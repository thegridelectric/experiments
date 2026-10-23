"""Emit this rehearsal's sema instance from its evidence.

- `instances/gw.experiment.run-001.json`: the one run, from the roll
  timeline's first and last marks (laptop clock, ET), the verdict and
  the executor claim the rehearsal tested.

    uv run python 2026-10-22-spruce-roll-rehearsal/emit_instances.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

MARK = re.compile(r"^T\d (\d{2}:\d{2}:\d{2}) ")
ET = ZoneInfo("America/New_York")
DAY = "2026-10-22"
INSTANCES = HERE / "instances"
TIMELINE = HERE / "evidence" / "roll-timeline.txt"
VERDICT = GwExperimentVerdict.Pass
CLAIM = 'wiki/gridworks-scada/executor/running.md "Rolling a house between lines"'
CODE_REF = "gridworks-scada eea7f97c (roll.sh as squashed; at run time the ssh -n and the event flush were still uncommitted on the laptop); spruce rolled to jm/spruce-unlimbo aa3b0709 and back to actual-spruce cda464ba"


def marks(path: Path) -> tuple[int, int]:
    found = []
    for line in path.read_text(errors="replace").splitlines():
        m = MARK.match(line)
        if m:
            found.append(int(datetime.fromisoformat(f"{DAY} {m.group(1)}").replace(tzinfo=ET).timestamp() * 1000))
    return found[0], found[-1]


def write(path: Path, word: GwExperimentRun) -> None:
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_dict(
        json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun
    )
    assert back == word, path
    print(path)


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    start, end = marks(TIMELINE)
    write(
        INSTANCES / "gw.experiment.run-001.json",
        GwExperimentRun(
            experiment_slug="spruce-roll-rehearsal",
            host_g_node_alias="hw1.isone.me.versant.keene.spruce.scada",
            start_unix_ms=start,
            end_unix_ms=end,
            code_ref=CODE_REF,
            verdict=VERDICT,
            claim=CLAIM,
        ),
    )


if __name__ == "__main__":
    main()
