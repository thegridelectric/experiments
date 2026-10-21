#!/usr/bin/env python3
"""Pull the LG heat pump channels of beech and oak from the journal DB
to one `-regen.npz` per house, in natural units.

One journal query spans one week (`grid.chunk_edges`; a month hits the
statement timeout). Each week's channel words come from the house's
own `layout.lite` at or before the week's end and each word's encoding
converts its values (`grid.natural`); relay channels keep their 0/1.
The database's unit column is never read. `forecast-oat` is no channel
word in either layout and is hand-mapped (FahrenheitX100, with the
stretch FOAT_X1000 where the journal holds it ten times larger).
Prints each week's layout.lite version and any channel a week lacks.

  uv run python pull.py --house beech > pull-beech.log
  uv run python pull.py --house oak > pull-oak.log

Unfinished: never run on the full window; the 2024-25 season (layout.lite 003) is outside it.
"""

import argparse
import datetime
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
sys.path.insert(2, str(HERE.parent / "dist-loop-experiments"))

from grid import chunk_edges, et_midnight_ms, natural  # noqa: E402  # pyright: ignore[reportMissingImports]  (dist-loop-experiments, on sys.path above)
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.enums import SpaceheatTelemetryName  # noqa: E402
from gwexp.sema.types import DataChannelGt  # noqa: E402
from lg_common import END, HAND_CHANNELS, START, WORD_CHANNELS, regen_path, ta_alias  # noqa: E402
from pull_readings import fetch_layout_channels, fetch_readings  # noqa: E402

# forecast-oat reads ten times its FahrenheitX100 value over this UTC
# stretch at both houses (24 °F reads 24000, against 2400 the day before);
# found in this pull, open with the journal's owner.
FOAT_X1000 = (
    int(datetime.datetime(2026, 1, 9, 2, tzinfo=datetime.timezone.utc).timestamp() * 1000),
    int(datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000),
)


def forecast_f(t_ms: np.ndarray, raw: np.ndarray) -> np.ndarray:
    """forecast-oat raw to °F, by the hand map."""
    scale = np.where((t_ms >= FOAT_X1000[0]) & (t_ms < FOAT_X1000[1]), 1000.0, 100.0)
    return raw / scale


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--house", required=True, choices=["beech", "oak"])
    args = p.parse_args()
    ta = ta_alias(args.house)
    codec = SemaCodec()
    t_parts: dict[str, list[np.ndarray]] = {}
    v_parts: dict[str, list[np.ndarray]] = {}
    edges = chunk_edges(START, END)
    for a, b in zip(edges, edges[1:]):
        a_ms, b_ms = et_midnight_ms(a), et_midnight_ms(b)
        print(f"{args.house} {a} -> {b}")
        try:
            words = fetch_layout_channels(ta, b_ms, codec)
        except SystemExit as no_layout:  # no layout.lite at or before the week end
            print(f"  skipped: {no_layout}")
            continue
        present = [n for n in WORD_CHANNELS if n in words]
        for n in WORD_CHANNELS:
            if n not in words:
                print(f"  {n}: no channel word this week")
        rows, _ = fetch_readings(ta, present + HAND_CHANNELS, [], a_ms, b_ms)
        for name, rs in rows.items():
            t = np.array([r[0] for r in rs], dtype=np.int64)
            raw = np.array([r[1] for r in rs], dtype=np.float64)
            if name in HAND_CHANNELS:
                v = forecast_f(t, raw)
            else:
                word = words[name]
                is_relay = isinstance(word, DataChannelGt) and word.telemetry_name == SpaceheatTelemetryName.RelayState
                v = raw if is_relay else natural(word, raw).astype(np.float64)
            t_parts.setdefault(name, []).append(t)
            v_parts.setdefault(name, []).append(v)
    out: dict[str, np.ndarray] = {}
    for name in t_parts:
        t = np.concatenate(t_parts[name])
        v = np.concatenate(v_parts[name])
        keep = np.r_[True, np.diff(t) > 0]  # time ordered, one value per instant
        out[f"{name}__t"], out[f"{name}__v"] = t[keep], v[keep]
        print(f"  {name}: {keep.sum()} readings")
    path = regen_path(args.house)
    np.savez_compressed(path, **out)  # pyright: ignore[reportArgumentType]
    print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
