"""Emit this run's sema instance from its evidence.

`instances/mm.induced.traces-gw.experiment.run-001.json`: the one run,
its window from `logs/maker-start.txt` and `logs/maker-stop.txt`, its
verdict from the capture holding exactly the glitch and nothing else out
of the maker.

    uv run python 2026-11-24-mm-induced-traces/emit_instances.py
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
CAPTURE = HERE / "captures" / "broker-capture-20261124-204022.jsonl"
MAKER = "d1.isone.me.versant.keene"
MIC = "mmmic_tx"
CODE = (
    "gridworks-marketmaker b19764c (jm/price-at-slot-open); "
    "gridworks-base 0.7.3; inject.py"
)


def mark(path: Path) -> int:
    return int(datetime.fromisoformat(path.read_text().strip()).timestamp() * 1000)


def verdict() -> GwExperimentVerdict:
    out = [
        json.loads(json.loads(line)["PayloadText"])
        for line in CAPTURE.read_text().splitlines()
        if json.loads(line)["Exchange"] == MIC
    ]
    glitches = [m for m in out if m["TypeName"] == "glitch"]
    ok = (
        len(out) == 1
        and len(glitches) == 1
        and glitches[0]["Summary"] == "no price to publish"
    )
    return GwExperimentVerdict.Pass if ok else GwExperimentVerdict.Fail


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    word = GwExperimentRun(
        experiment_slug="mm-induced-traces",
        host_g_node_alias=MAKER,
        start_unix_ms=mark(LOGS / "maker-start.txt"),
        end_unix_ms=mark(LOGS / "maker-stop.txt"),
        code_ref=CODE,
        verdict=verdict(),
        claim=(
            "wiki/gridworks-marketmaker/executor/Clauses.yaml "
            "hub 1b, inbox 1a, gate 3c"
        ),
    )
    path = INSTANCES / "mm.induced.traces-gw.experiment.run-001.json"
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_dict(
        json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun
    )
    assert back == word, path
    print(path)


if __name__ == "__main__":
    main()
