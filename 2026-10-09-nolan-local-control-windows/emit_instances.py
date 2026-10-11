"""Emit this window's sema instances from its evidence.

- `instances/gw.experiment.run-00N.json`: one per window, from its boot
  log's first and last stamps (box clock, ET in the log, converted), the
  verdict and the executor claim the window tested (`<file> "<section>"`). 001 spruce morning, 002
  spruce afternoon, 003 beech afternoon (the full 20 minutes).

    uv run python emit_instances.py
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
RUNS = [
    (
        "001",
        HERE / "evidence" / "spruce-window-boot.log",
        "hw1.isone.me.versant.keene.spruce.scada",
        "gridworks-scada 97ea5806 (jm/spruce-unlimbo); experiments 1e5bd72 spruce_window.sh on 15",
        'wiki/gridworks-scada/executor/local-control.md "The Nolan heating machine"',
    ),
    (
        "002",
        HERE / "evidence" / "run2" / "spruce-window-boot.log",
        "hw1.isone.me.versant.keene.spruce.scada",
        "gridworks-scada 97ea5806 (jm/spruce-unlimbo); experiments 1e5bd72 spruce_window.sh on 25",
        'wiki/gridworks-scada/executor/local-control.md "The Nolan heating machine"',
    ),
    (
        "003",
        HERE / "evidence" / "run2" / "beech-window-boot.log",
        "hw1.isone.me.versant.keene.beech.scada",
        "gridworks-scada 97ea5806 (jm/spruce-unlimbo); experiments 1e5bd72 beech_window.sh on 20, both pis",
        'wiki/gridworks-scada/executor/local-control.md "Standby"',
    ),
]


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
    for number, boot_log, host, code_ref, claim in RUNS:
        start, end = stamps(boot_log)
        write(
            INSTANCES / f"gw.experiment.run-{number}.json",
            GwExperimentRun(
                experiment_slug="nolan-local-control-windows",
                host_g_node_alias=host,
                start_unix_ms=start,
                end_unix_ms=end,
                code_ref=code_ref,
                verdict=GwExperimentVerdict.Pass,
                claim=claim,
            ),
        )


if __name__ == "__main__":
    main()
