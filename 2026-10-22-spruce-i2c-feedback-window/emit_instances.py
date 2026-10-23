"""Emit this window's sema instance from its evidence.

- `instances/gw.experiment.run-001.json`: the one window, from the boot
  log's first and last stamps (box clock, ET in the log, converted), the
  verdict and the executor claim the window tested.

    uv run python 2026-10-22-spruce-i2c-feedback-window/emit_instances.py
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

STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) ")
ET = ZoneInfo("America/New_York")
INSTANCES = HERE / "instances"
BOOT_LOG = HERE / "evidence" / "spruce-window-20261022-082343.log"
VERDICT = GwExperimentVerdict.Pass
CLAIM = 'wiki/gridworks-scada/executor/control-hierarchy.md "Confirmation belongs to the relay actor, per board"'
CODE_REF = "gridworks-scada aa3b0709 (jm/spruce-unlimbo); spruce_window.sh on 11; admin_drive.py hp:off then 6 x (valve:iso:close, valve:iso:open) 5 s apart, release"


def stamps(path: Path) -> tuple[int, int]:
    found = []
    for line in path.read_text(errors="replace").splitlines():
        m = STAMP.match(line)
        if m:
            found.append(int(datetime.fromisoformat(m.group(1)).replace(tzinfo=ET).timestamp() * 1000))
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
    start, end = stamps(BOOT_LOG)
    write(
        INSTANCES / "gw.experiment.run-001.json",
        GwExperimentRun(
            experiment_slug="spruce-i2c-feedback-window",
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
