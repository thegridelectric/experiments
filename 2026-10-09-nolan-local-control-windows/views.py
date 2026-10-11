"""Display CSVs for the nolan-local-control windows (gitignored, regenerated).

    uv run python views.py runs       # runs-display.csv, from instances/
    uv run python views.py glitches   # glitches-display.csv, from both captures

`runs` decodes each `gw.experiment.run` instance through the codec: one
row per window with its host, ET bounds, length, verdict and claim.

`glitches` decodes every `glitch` the window scadas published, from the
morning capture and the afternoon one (`evidence/run2/capture.jsonl.gz`),
one row per glitch in time order. A capture line is the broker's view of
one publish; its `PayloadText` is the scada's Header/Payload envelope, and
the payload is the sema word.
"""

import csv
import gzip
import json
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.types import Glitch, GwExperimentRun  # noqa: E402

ET = ZoneInfo("America/New_York")
CAPTURES = [
    ("run1", HERE / "evidence" / "capture.jsonl"),
    ("run2", HERE / "evidence" / "run2" / "capture.jsonl.gz"),
]


def et(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, ET).strftime("%H:%M:%S")


def capture_lines(path: Path) -> Iterator[str]:
    """A capture's lines, from the plain file or its gzipped form."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as f:
            yield from f
    else:
        with path.open() as f:
            yield from f


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(path)


def runs() -> None:
    rows: list[list[object]] = []
    for p in sorted((HERE / "instances").glob("gw.experiment.run-*.json")):
        run = default_codec.from_dict(json.loads(p.read_text()), expect=GwExperimentRun)
        rows.append(
            [
                p.stem.rsplit("-", 1)[1],
                run.host_g_node_alias,
                et(run.start_unix_ms),
                et(run.end_unix_ms),
                round((run.end_unix_ms - run.start_unix_ms) / 60000, 1),
                run.verdict.value,
                run.claim,
            ]
        )
    write_csv(
        HERE / "runs-display.csv",
        ["run", "host", "start_et", "end_et", "minutes", "verdict", "claim"],
        rows,
    )


def glitches() -> None:
    found: list[tuple[str, Glitch]] = []
    for label, path in CAPTURES:
        for line in capture_lines(path):
            envelope = json.loads(json.loads(line)["PayloadText"])
            payload = envelope.get("Payload", {})
            if payload.get("TypeName") == "glitch":
                found.append((label, default_codec.from_dict(payload, expect=Glitch)))
    found.sort(key=lambda lg: lg[1].created_ms)
    write_csv(
        HERE / "glitches-display.csv",
        ["capture", "created_et", "from", "node", "level", "summary", "details"],
        [
            [label, et(g.created_ms), g.from_g_node_alias, g.node, g.type.value,
             g.summary, g.details]
            for label, g in found
        ],
    )


def main() -> None:
    view = sys.argv[1] if len(sys.argv) > 1 else ""
    if view == "runs":
        runs()
    elif view == "glitches":
        glitches()
    else:
        sys.exit("usage: views.py runs|glitches")


if __name__ == "__main__":
    main()
