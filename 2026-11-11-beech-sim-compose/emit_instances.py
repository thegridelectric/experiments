"""Emit this run's sema instance from its evidence.

- `instances/beech.sim.compose-gw.experiment.run-001.json`: the one run,
  from the moment the scada's container was created to the moment of the
  check, its verdict from `logs/check.json`, its code from
  `logs/code-under-test.txt`.

    uv run python 2026-11-11-beech-sim-compose/emit_instances.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

LOGS = HERE / "logs"
INSTANCES = HERE / "instances"
SCADA_ALIAS = "d1.isone.me.versant.keene.beech.scada"
VERDICTS = {"PASS": GwExperimentVerdict.Pass, "FAIL": GwExperimentVerdict.Fail}
DOCKER_TIME = "%Y-%m-%d %H:%M:%S %z %Z"


def unix_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    check = json.loads((LOGS / "check.json").read_text())
    code = "; ".join((LOGS / "code-under-test.txt").read_text().splitlines())
    word = GwExperimentRun(
        experiment_slug="beech-sim-compose",
        host_g_node_alias=SCADA_ALIAS,
        start_unix_ms=unix_ms(
            datetime.strptime(check["services_created_at"]["scada"], DOCKER_TIME)
        ),
        end_unix_ms=unix_ms(datetime.fromisoformat(check["checked_at_utc"])),
        code_ref=f"{code}; compose.yaml, check.py, stack_check.py",
        verdict=VERDICTS[check["verdict"]],
    )
    path = INSTANCES / "beech.sim.compose-gw.experiment.run-001.json"
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_dict(
        json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun
    )
    assert back == word, path
    print(path)


if __name__ == "__main__":
    main()
