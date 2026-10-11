"""Emit this run's sema instances from its evidence.

- `instances/hw1.alerts-<door>.<state>-gw.alert-000.json`: the prober's
  `BrokerUnreachable` transitions, one Firing and one Resolved per door,
  as the alerter's store held them (`evidence/alerter-store-alerts.json`).
- `instances/gw.experiment.run-001.json`: the window from the broker stop
  (18:18:04Z) to the last MQTT
  client accepted back, both read off `evidence/broker-log-reduced.txt`
  (the broker's own SIGTERM line and its last MQTT accept), the verdict
  and the claim it stamps.

    uv run python emit_instances.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec
from gwexp.sema.enums import GwExperimentVerdict
from gwexp.sema.types import GwAlert, GwExperimentRun

EVIDENCE = HERE / "evidence"
INSTANCES = HERE / "instances"
CLAIM = 'wiki/gridworks-alerter/executor/gwalerter.md "The prober"'
CODE_REF = "prod broker hw1-1 docker compose stop/start; alerter-probe on alerts (gridworks-alerter d61c4dd)"


def write(path: Path, word) -> None:
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_bytes(path.read_bytes())
    assert back == word, path
    print(path)


def alert_filename(word: GwAlert) -> str:
    assert word.subject is not None, word.alert_id
    door = word.subject.replace(":", ".").replace("-", ".")
    return f"{word.src}-{door}.{word.state.value.lower()}-{word.type_name}-{word.version}.json"


def log_ms(marker: str, last: bool) -> int:
    """Broker-log time of the first (or last) line containing `marker`."""
    lines = [
        ln
        for ln in (EVIDENCE / "broker-log-reduced.txt").read_text().splitlines()
        if marker in ln and not ln.startswith("#")
    ]
    line = lines[-1] if last else lines[0]
    return int(
        datetime.fromisoformat(line.split(" [")[0].replace(" ", "T")).timestamp()
        * 1000
    )


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    for row in json.loads((EVIDENCE / "alerter-store-alerts.json").read_text()):
        for raw in (row["payload"], row["resolved_payload"]):
            if raw is not None:
                word = default_codec.from_dict(raw, expect=GwAlert)
                write(INSTANCES / alert_filename(word), word)
    write(
        INSTANCES / "gw.experiment.run-001.json",
        GwExperimentRun(
            experiment_slug="prod-broker-outage-drill",
            host_g_node_alias="hw1.alerts",
            start_unix_ms=log_ms("SIGTERM received", last=False),
            end_unix_ms=log_ms("Accepted MQTT", last=True),
            code_ref=CODE_REF,
            verdict=GwExperimentVerdict.Pass,
            claim=CLAIM,
        ),
    )


if __name__ == "__main__":
    main()
