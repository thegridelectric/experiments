"""Emit the gw.experiment.run instances for the two windows of this
experiment, one per window, from the window scada's own log (the box's
clock, ET): start is the first stamped line, end the last. Each instance
is built through the vendored gwexp snapshot class, written as its dict
form, and read back through the codec so the file on disk is what
validates.

    python emit_instances.py
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
ALIAS = "hw1.isone.me.versant.keene.maple.scada"
CODE_REF = "gridworks-scada b347d2f0; experiments 9e0d91b drive_keep_ratio.py maple"
WINDOWS = [
    ("maple-window-20260928-193926.log", "gw.experiment.run-000.json"),
    ("maple-window-20260928-210651.log", "gw.experiment.run-001.json"),
]


def stamp_ms(line: str) -> int:
    m = STAMP.match(line)
    if m is None:
        raise ValueError(f"no box stamp on: {line}")
    return int(datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{BOX_OFFSET}").timestamp() * 1000)


def bounds(path: Path) -> tuple[int, int]:
    stamps = [stamp_ms(x) for x in path.read_text().splitlines() if STAMP.match(x)]
    return stamps[0], stamps[-1]


def main() -> None:
    codec = SemaCodec()
    (HERE / "instances").mkdir(exist_ok=True)
    for log, name in WINDOWS:
        start, end = bounds(HERE / log)
        run = GwExperimentRun(
            experiment_slug="sieg-keep-ratio-map",
            host_g_node_alias=ALIAS,
            start_unix_ms=start,
            end_unix_ms=end,
            code_ref=CODE_REF,
        )
        out = HERE / "instances" / name
        out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
        back = codec.from_dict(json.loads(out.read_text()), expect=GwExperimentRun)
        print(out.name, back.start_unix_ms, back.end_unix_ms)


if __name__ == "__main__":
    main()
