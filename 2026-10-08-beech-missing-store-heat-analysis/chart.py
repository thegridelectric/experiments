"""Chart beech's night of 2026-01-04/05: water temperatures against the
buffer-full threshold, store temperatures, heat flows, and control state.

Reads the display CSV (regenerate it from the gw.readings instance, see the
README) and the journal payloads in ./evidence/ (fetch_messages.py), decoded
through the vendored sema snapshot at the versions beech sent that night.
Writes beech-night-control-state.png.

    uv run python chart.py
"""

import csv
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, TypeVar
from zoneinfo import ZoneInfo

import matplotlib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gwexp.sema.base import SemaType  # noqa: E402
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import HeatingForecast  # noqa: E402
from gwexp.sema.types.old_versions.layout_lite_006 import LayoutLite006  # noqa: E402
from gwexp.sema.types.old_versions.report_event_002 import ReportEvent002  # noqa: E402

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
CSV = HERE / "instances" / "hw1.isone.me.versant.keene.beech.ta-gw.readings-000-display.csv"
EVIDENCE = HERE / "evidence"
OUT = HERE / "beech-night-control-state.png"
ET = ZoneInfo("America/New_York")
T0 = datetime(2026, 1, 4, 18, tzinfo=ET)
T1 = datetime(2026, 1, 5, 10, tzinfo=ET)
TRAP = (datetime(2026, 1, 4, 21, 44, 21, tzinfo=ET), datetime(2026, 1, 5, 3, 52, 50, tzinfo=ET))
MAX_EWT_F = 166  # Ha1Params.MaxEwtF in layout.lite; check_inputs() asserts it

# reference palette, categorical slots 1-4 (validated light; direct labels carry identity)
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3dd", "#fcfcfb"
BAND = "#efeee9"


class Point(NamedTuple):
    """One reading: ET time and natural-unit value."""
    t: datetime
    v: float


def readings() -> dict[str, list[Point]]:
    out: dict[str, list[Point]] = {}
    with open(CSV) as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["timestamp_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            out.setdefault(r["channel"], []).append(Point(t, float(r["value"])))
    return out


def minute_means(pts: list[Point]) -> list[Point]:
    bins: dict[datetime, list[float]] = {}
    for p in pts:
        bins.setdefault(p.t.replace(second=0), []).append(p.v)
    return [Point(t, sum(v) / len(v)) for t, v in sorted(bins.items())]


def ffill(pts: list[Point], grid: list[datetime]) -> list[float | None]:
    out: list[float | None] = []
    j, v = 0, None
    for g in grid:
        while j < len(pts) and pts[j].t <= g:
            v = pts[j].v
            j += 1
        out.append(v)
    return out


M = TypeVar("M", bound=SemaType)


def payloads(type_name: str, expect: type[M]) -> list[M]:
    """The evidence file's messages decoded at the version beech sent, not upgraded."""
    codec = SemaCodec()
    with gzip.open(EVIDENCE / f"beech.scada-{type_name}.jsonl.gz", "rt") as f:
        return [codec.from_dict(json.loads(line), auto_upgrade=False, expect=expect) for line in f]


def check_inputs() -> None:
    params = [p.ha1_params.max_ewt_f for p in payloads("layout.lite", LayoutLite006)]
    assert set(params) == {MAX_EWT_F}, params


def full_threshold() -> list[Point]:
    """Pre-fix buffer-full threshold: max of the next three forecast RSWTs, uncapped."""
    return [Point(datetime.fromtimestamp(p.forecast_created_s, ET), max(p.rswt_f[:3]))
            for p in payloads("heating.forecast", HeatingForecast)]


def states() -> dict[str, list[tuple[datetime, str]]]:
    """Change points per row of the state band; relay3 merges its auto and admin handles."""
    rows = {"Local Control state": [("ha.winter.state", "auto.h.n")],
            "Top state": [("top.state", "s")],
            "Store valve (relay3)": [("store.flow.relay", "auto.h.n.relay3"),
                                     ("store.flow.relay", "admin.relay3")]}
    raw: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for rep in payloads("report.event", ReportEvent002):
        for s in rep.report.state_list:
            raw.setdefault((s.state_enum, s.machine_handle), []).extend(
                zip(s.unix_ms_list, s.state_list))
    out: dict[str, list[tuple[datetime, str]]] = {}
    for row, keys in rows.items():
        pts = sorted(p for k in keys for p in raw.get(k, []))
        seq: list[tuple[datetime, str]] = []
        for ms, st in pts:
            if not seq or seq[-1][1] != st:
                seq.append((datetime.fromtimestamp(ms / 1000, ET), st))
        out[row] = seq
    return out


def label_end(ax, pts: list[Point] | list[tuple[datetime, float]], text: str, color: str, dy: float = 0) -> None:
    t, v = pts[-1]
    ax.annotate(text, (t, v), xytext=(4, dy), textcoords="offset points", color=INK2,
                fontsize=8, va="center")
    ax.plot([t], [v], marker="o", ms=3, color=color)


def style(ax, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.axvspan(*TRAP, color=BAND, zorder=0)


def main() -> None:
    check_inputs()
    r = readings()
    fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2, 2, 1.3]})
    fig.patch.set_facecolor(SURFACE)

    # 1. buffer and heat-pump water against the full threshold
    ax = axes[0]
    style(ax, "°F")
    for ch, color, name, dy in [("hp-lwt", ORANGE, "HP leaving", 5), ("hp-ewt", YELLOW, "HP entering", -5),
                                ("buffer-depth1", AQUA, "buffer top", 0),
                                ("buffer-depth3", BLUE, "buffer bottom (tested)", 0)]:
        pts = minute_means([p for p in r[ch] if T0 <= p.t < T1])
        ax.plot([p.t for p in pts], [p.v for p in pts], color=color, lw=1.6 if ch == "buffer-depth3" else 1.1)
        label_end(ax, pts, name, color, dy)
    thr = [p for p in full_threshold() if p.t < T1]
    xs = [T0] + [p.t for p in thr] + [T1]
    ys = [thr[0].v] + [p.v for p in thr] + [thr[-1].v]
    ax.step(xs, ys, where="post", color=INK, lw=1.2, ls="--")
    at = datetime(2026, 1, 5, 4, 15, tzinfo=ET)
    ax.annotate("buffer-full threshold as run: max next-3h forecast RSWT", (at, 178.9), xytext=(0, 6),
                textcoords="offset points", fontsize=8, color=INK)
    ax.axhline(MAX_EWT_F, color=INK2, lw=1, ls=":")
    ax.annotate(f"MaxEwtF {MAX_EWT_F} °F: the cap the Jan 5 patch added", (datetime(2026, 1, 5, 7, 15, tzinfo=ET), MAX_EWT_F), xytext=(0, -11),
                textcoords="offset points", fontsize=8, color=INK2)
    ax.set_ylim(60, 195)
    ax.set_title("Beech, night of Jan 4–5 2026: Local Control held the heat pump on the buffer, store uncharged",
                 loc="left", fontsize=11, color=INK)

    # 2. store
    ax = axes[1]
    style(ax, "°F")
    for ch, color, name in [("tank1-depth1", BLUE, "tank1 top"), ("tank2-depth1", ORANGE, "tank2 top"),
                            ("tank3-depth3", AQUA, "tank3 bottom")]:
        pts = minute_means([p for p in r[ch] if T0 <= p.t < T1])
        ax.plot([p.t for p in pts], [p.v for p in pts], color=color, lw=1.2)
        label_end(ax, pts, name, color)

    # 3. heat flows, 5-minute means
    ax = axes[2]
    style(ax, "kW")
    grid = [datetime.fromtimestamp(T0.timestamp() + 10 * i, ET)
            for i in range(int((T1 - T0).total_seconds() // 10))]
    F = {c: ffill(sorted(r[c]), grid) for c in ("primary-flow", "hp-lwt", "hp-ewt", "dist-flow",
                                                 "dist-swt", "dist-rwt", "hp-odu-pwr", "hp-idu-pwr")}

    def heat_kw(flow: str, hot: str, cold: str, i: int) -> float | None:
        a, b, c = F[flow][i], F[hot][i], F[cold][i]
        return None if None in (a, b, c) else 500 * a * (b - c) / 3412

    def elec_kw(i: int) -> float | None:
        a, b = F["hp-odu-pwr"][i], F["hp-idu-pwr"][i]
        return None if None in (a, b) else (a + b) / 1000

    series = {"HP heat out": (ORANGE, 6, lambda i: heat_kw("primary-flow", "hp-lwt", "hp-ewt", i)),
              "HP electric": (YELLOW, -5, elec_kw),
              "to distribution": (BLUE, 0, lambda i: heat_kw("dist-flow", "dist-swt", "dist-rwt", i))}
    for name, (color, dy, fn) in series.items():
        pts: list[Point] = []
        for k in range(0, len(grid), 30):
            vals = [v for i in range(k, min(k + 30, len(grid))) if (v := fn(i)) is not None]
            if vals:
                pts.append(Point(grid[k], sum(vals) / len(vals)))
        ax.plot([p.t for p in pts], [p.v for p in pts], color=color, lw=1.2)
        label_end(ax, pts, name, color, dy)

    # 4. control state band
    ax = axes[3]
    style(ax, "")
    ax.grid(False)
    tones = {"HpOnStoreCharge": BLUE, "ChargingStore": BLUE, "HpOnStoreOff": ORANGE,
             "DischargingStore": "#c9c7bd", "Admin": YELLOW}
    rows = states()
    for y, (row, seq) in enumerate(reversed(list(rows.items()))):
        for k, (t, st) in enumerate(seq):
            end = seq[k + 1][0] if k + 1 < len(seq) else T1
            t = max(t, T0)
            if end <= t:
                continue
            ax.barh(y, end - t, left=t, height=0.6, color=tones.get(st, "#dcdad3"),
                    edgecolor=SURFACE, lw=2)
            if (end - t).total_seconds() > 3600:
                ax.text(t + (end - t) / 2, y, st, ha="center", va="center", fontsize=7.5, color=INK)
    ax.set_yticks(range(len(rows)), list(reversed(list(rows))), fontsize=8, color=INK2)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=ET))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2, tz=ET))
    ax.set_xlim(T0, T1)
    ax.set_xlabel("ET (shaded: 21:44–03:52, HpOnStoreOff until the Admin takeover)", color=INK2, fontsize=8)

    fig.subplots_adjust(right=0.86, hspace=0.12, left=0.13, top=0.95, bottom=0.06)
    fig.savefig(OUT, dpi=140, facecolor=SURFACE)
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
