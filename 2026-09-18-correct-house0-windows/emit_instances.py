"""Emit the gw.experiment.run instances for the two correct-house0 windows.

One instance per house. Start and end come from the window scada's own log
(the file copied into this folder by `house_window.sh <house> off`): start is
the first stamped line, end is the last. Those stamps are the box clock, local
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

WINDOWS = {
    "spruce": (
        "hw1.isone.me.versant.keene.spruce.scada",
        "spruce-window-20260918-192107.log",
    ),
    "beech": (
        "hw1.isone.me.versant.keene.beech.scada",
        "beech-window-20260918-194106.log",
    ),
}


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


def main() -> None:
    codec = SemaCodec()
    for house, (alias, log_name) in WINDOWS.items():
        log = HERE / log_name
        if not log.exists():
            print(f"skip {house}: {log_name} not in the folder")
            continue
        start, end = bounds(log)
        run = GwExperimentRun(
            experiment_slug="correct-house0-windows",
            host_g_node_alias=alias,
            start_unix_ms=start,
            end_unix_ms=end,
            code_ref=f"gridworks-scada cd34f5ef; experiments 5c30b84 house_window.sh {house}",
        )
        out = HERE / f"instances/{house}-gw.experiment.run-000.json"
        out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
        back = codec.from_dict(json.loads(out.read_text()), expect=GwExperimentRun)
        print(out.name, back.start_unix_ms, back.end_unix_ms)


if __name__ == "__main__":
    main()
