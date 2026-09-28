"""Emit the gw.experiment.run instance for this window.

Start and end come from the maple window scada's own log (the file
`house_window.sh maple off` copied here): start is the first stamped line,
end is the last. The stamps are the box clock, local ET, about 70 seconds
behind the laptop clock.

The instance is constructed through the vendored gwexp snapshot class,
written as its dict form, then read back through the codec so the file on
disk is what validates.
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
LOG = "maple-window-20260928-071602.log"
ALIAS = "hw1.isone.me.versant.keene.maple.scada"
CODE_REF = "gridworks-scada b9679d4e; experiments 65f0a25 house_window.sh maple"


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
    start, end = bounds(HERE / LOG)
    run = GwExperimentRun(
        experiment_slug="maple-ecodan-start-in-full-keep",
        host_g_node_alias=ALIAS,
        start_unix_ms=start,
        end_unix_ms=end,
        code_ref=CODE_REF,
    )
    out = HERE / "instances/gw.experiment.run-000.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
    back = codec.from_dict(json.loads(out.read_text()), expect=GwExperimentRun)
    print(out.name, back.start_unix_ms, back.end_unix_ms)


if __name__ == "__main__":
    main()
