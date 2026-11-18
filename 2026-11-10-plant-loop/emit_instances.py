"""Emit each run's sema instance from its evidence.

- `instances/plant.loop-gw.experiment.run-001.json`: the hazel run, from
  `logs/`.

A run's window is the first and last marks of its `clock.txt`, its verdict
is its `loop.json`'s and its code is its `code-under-test.txt`.

`instances/plant.loop-gw.experiment.run-002.json`, the orange run, is not
emitted here: the files it was emitted from are not kept.

    uv run python 2026-11-10-plant-loop/emit_instances.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

INSTANCES = HERE / "instances"


class Run(NamedTuple):
    """One run of the loop: where its evidence is and the scada it ran
    as. Interior to this emitter; `gw.experiment.run` is the word."""

    number: str
    logs: Path
    scada_alias: str


RUNS = [
    Run("001", HERE / "logs", "d1.isone.ct.newhaven.hazel1.scada"),
]
VERDICTS = {"PASS": GwExperimentVerdict.Pass, "FAIL": GwExperimentVerdict.Fail}


def marks(path: Path) -> tuple[int, int]:
    stamps = [
        int(datetime.fromisoformat(line.split(" ", 1)[0]).timestamp() * 1000)
        for line in path.read_text().splitlines()
    ]
    return stamps[0], stamps[-1]


def emit(run: Run) -> Path:
    start, end = marks(run.logs / "clock.txt")
    code = "; ".join((run.logs / "code-under-test.txt").read_text().splitlines())
    word = GwExperimentRun(
        experiment_slug="plant-loop",
        host_g_node_alias=run.scada_alias,
        start_unix_ms=start,
        end_unix_ms=end,
        code_ref=f"{code}; run.sh, loop_check.py",
        verdict=VERDICTS[json.loads((run.logs / "loop.json").read_text())["verdict"]],
    )
    path = INSTANCES / f"plant.loop-gw.experiment.run-{run.number}.json"
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_dict(
        json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun
    )
    assert back == word, path
    return path


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    for run in RUNS:
        print(emit(run))


if __name__ == "__main__":
    main()
