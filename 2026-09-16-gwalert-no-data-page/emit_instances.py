"""Emit instances/gw.experiment.run-000.json for the gwalert no-data page run.

The window is read from the evidence: start is the `Stopping gwspaceheat`
line on spruce (box clock ET, ISO offset in the line), end is the first
gwalert cycle after the restart that sees spruce data under a minute old
(box clock UTC).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.types import GwExperimentRun  # noqa: E402

STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:?\d{2})")


def stamp_ms(line: str) -> int:
    m = STAMP.match(line)
    if m is None:
        raise ValueError(f"no ISO stamp on: {line}")
    s = m.group(1)
    if s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    return int(datetime.fromisoformat(s).timestamp() * 1000)


def first_line(path: Path, pattern: str) -> str:
    for line in path.read_text().splitlines():
        if re.search(pattern, line):
            return line
    raise ValueError(f"{path}: no line matching {pattern!r}")


def main() -> None:
    start = stamp_ms(first_line(HERE / "evidence/spruce-journal.log", r"Stopping gwspaceheat"))
    end = stamp_ms(first_line(HERE / "evidence/alerts-journal.log", r"spruce: Found data up to 0\.\d minutes"))
    run = GwExperimentRun(
        experiment_slug="gwalert-no-data-page",
        host_g_node_alias="hw1.alerts",
        start_unix_ms=start,
        end_unix_ms=end,
        code_ref="gridworks-alerts e3e9b47; run.sh",
    )
    out = HERE / "instances/gw.experiment.run-000.json"
    out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
    print(out, run.start_unix_ms, run.end_unix_ms)


if __name__ == "__main__":
    main()
