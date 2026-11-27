"""Emit this run's sema instance from its evidence.

- `instances/plant.crossing-gw.experiment.run-001.json`: the one run, its
  window from the first and last marks of `logs/clock.txt`, its verdict
  from `logs/crossing.json`, its code from `logs/code-under-test.txt`.

    uv run python 2026-11-10-plant-crossing/emit_instances.py
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
SCADA_ALIAS = "d1.isone.ct.newhaven.hazel1.scada"
VERDICTS = {"PASS": GwExperimentVerdict.Pass, "FAIL": GwExperimentVerdict.Fail}


def marks(path: Path) -> tuple[int, int]:
    stamps = [
        int(datetime.fromisoformat(line.split(" ", 1)[0]).timestamp() * 1000)
        for line in path.read_text().splitlines()
    ]
    return stamps[0], stamps[-1]


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    start, end = marks(LOGS / "clock.txt")
    code = "; ".join((LOGS / "code-under-test.txt").read_text().splitlines())
    word = GwExperimentRun(
        experiment_slug="plant-crossing",
        host_g_node_alias=SCADA_ALIAS,
        start_unix_ms=start,
        end_unix_ms=end,
        code_ref=f"{code}; run.sh, crossing.py",
        verdict=VERDICTS[json.loads((LOGS / "crossing.json").read_text())["verdict"]],
    )
    path = INSTANCES / "plant.crossing-gw.experiment.run-001.json"
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_dict(
        json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun
    )
    assert back == word, path
    print(path)


if __name__ == "__main__":
    main()
