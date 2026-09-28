"""Emit instances/gw.experiment.run-000.json for the 2026-09-28 run.

The window is read from the evidence: start is the first alerter's log
header (`started=`), end is the last line of the alerter file log (the
Resolved record), both UTC. The instance is written as its dict form and
read back through the codec, so the file on disk is what validates.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

EVIDENCE = HERE / "evidence/2026-09-28/alerter-file.log"
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)")


def stamp_ms(line: str) -> int:
    m = STAMP.search(line)
    if m is None:
        raise ValueError(f"no UTC stamp on: {line}")
    return int(datetime.fromisoformat(m.group(1)).timestamp() * 1000)


def main() -> None:
    lines = EVIDENCE.read_text().splitlines()
    run = GwExperimentRun(
        experiment_slug="alerter-no-data",
        host_g_node_alias="d1.alerts",
        start_unix_ms=stamp_ms(lines[0]),
        end_unix_ms=stamp_ms(lines[-1]),
        code_ref="gridworks-alerter d29d9a6 (jm/gw-alert); run.sh",
    )
    out = HERE / "instances/gw.experiment.run-000.json"
    out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
    back = default_codec.from_bytes(out.read_bytes())
    assert isinstance(back, GwExperimentRun) and back == run
    print(out, run.start_unix_ms, run.end_unix_ms)


if __name__ == "__main__":
    main()
