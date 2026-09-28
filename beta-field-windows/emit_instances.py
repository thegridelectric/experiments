"""Emit the gw.experiment.run instances for a round's two windows.

One instance per house. Start and end come from the window scada's own log
(the `<house>-window-*.log` the run folder holds, copied there from
`house_window.sh <house> off`): start is the first stamped line, end is the
last.

    uv run python beta-field-windows/emit_instances.py <run folder> "<code ref>"
 Those stamps are the box clock, local
ET, which runs about 70 seconds behind the laptop clock.

Each instance is constructed through the vendored gwexp snapshot class, written
as its dict form, then read back through the codec so the file on disk is what
validates.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

BOX_OFFSET = "-04:00"
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}\.\d{3})")

ALIASES = {
    "spruce": "hw1.isone.me.versant.keene.spruce.scada",
    "beech": "hw1.isone.me.versant.keene.beech.scada",
    "maple": "hw1.isone.me.versant.keene.maple.scada",
}


def window_logs(folder: Path) -> dict[str, tuple[str, str]]:
    """The run's log per house: `<house>-window-*.log` in the run folder."""
    found = {}
    for house, alias in ALIASES.items():
        logs = sorted(folder.glob(f"{house}-window-*.log"))
        if logs:
            found[house] = (alias, logs[-1].name)
    return found


def stamp_ms(line: str) -> int:
    m = STAMP.match(line)
    if m is None:
        raise ValueError(f"no box stamp on: {line}")
    return int(
        datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{BOX_OFFSET}").timestamp()
        * 1000
    )


def bounds(path: Path) -> tuple[int, int]:
    stamps = [stamp_ms(x) for x in path.read_text().splitlines() if STAMP.match(x)]
    if not stamps:
        raise ValueError(f"{path}: no stamped lines")
    return stamps[0], stamps[-1]


def main(folder: Path, code_ref: str) -> None:
    codec = SemaCodec()
    for house, (alias, log_name) in window_logs(folder).items():
        log = folder / log_name
        start, end = bounds(log)
        run = GwExperimentRun(
            experiment_slug="beta-field-windows",
            host_g_node_alias=alias,
            start_unix_ms=start,
            end_unix_ms=end,
            code_ref=f"{code_ref} house_window.sh {house}",
        )
        out = folder / f"instances/{house}-gw.experiment.run-000.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
        back = codec.from_dict(json.loads(out.read_text()), expect=GwExperimentRun)
        print(out.name, back.start_unix_ms, back.end_unix_ms)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), sys.argv[2])
