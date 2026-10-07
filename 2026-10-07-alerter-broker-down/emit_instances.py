"""Emit this run's sema instances from its evidence.

- `instances/d1.alerts-<door>-<state>-gw.alert-000.json`: the prober's
  `BrokerUnreachable` transitions, one Firing and one Resolved per door,
  read from the alerter's store as archived (`evidence/<date>/
  alerter.sqlite`); subject the alerter's alias, condition the door as
  `host.port` plus the state. Any `NoData` record in the store is
  emitted too (`<house>-<state>-gw.alert-000.json`); the bar is that
  there is none.
- `instances/d1.alerts-tiny<N>-gw.opsgenie.alert-000.json`: one per
  alert Opsgenie listed at the end (`evidence/<date>/
  opsgenie-final.json`).
- `instances/gw.experiment.run-001.json`: the run window from the
  alerter file log, the verdict and the claim it stamps.

    uv run python emit_instances.py [evidence/2026-10-07]
"""

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwAlert, GwExperimentRun  # noqa: E402
from opsgenie_listing import from_listing  # noqa: E402

STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)")
INSTANCES = HERE / "instances"
CLAIM = 'wiki/gridworks-alerter/executor/gwalerter.md "The prober"'


def stamp_ms(line: str) -> int:
    m = STAMP.search(line)
    if m is None:
        raise ValueError(f"no UTC stamp on: {line}")
    return int(datetime.fromisoformat(m.group(1)).timestamp() * 1000)


def write(path: Path, word) -> None:
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_bytes(path.read_bytes())
    assert back == word, path
    print(path)


def alert_words(store: Path) -> list[GwAlert]:
    rows = sqlite3.connect(store).execute(
        "select payload, resolved_payload from alerts order by raised_ms"
    )
    words: list[GwAlert] = []
    for payload, resolved_payload in rows:
        for raw in (payload, resolved_payload):
            if raw is not None:
                words.append(default_codec.from_dict(json.loads(raw), expect=GwAlert))
    return words


def alert_filename(word: GwAlert) -> str:
    state = word.state.value.lower()
    if word.about_g_node_alias is not None:
        return f"{word.about_g_node_alias}-{state}-{word.type_name}-{word.version}.json"
    door = (word.subject or "").replace(":", ".").replace("-", ".")
    return f"{word.src}-{door}.{state}-{word.type_name}-{word.version}.json"


def main(evidence: Path, verdict: GwExperimentVerdict) -> None:
    INSTANCES.mkdir(exist_ok=True)
    for word in alert_words(evidence / "alerter.sqlite"):
        write(INSTANCES / alert_filename(word), word)
    listing = json.loads((evidence / "opsgenie-final.json").read_text())
    for og in from_listing(listing):
        write(
            INSTANCES / f"{og.source}-tiny{og.tiny_id}-{og.type_name}-{og.version}.json",
            og,
        )
    lines = (evidence / "d1.alerts.log").read_text().splitlines()
    write(
        INSTANCES / "gw.experiment.run-001.json",
        GwExperimentRun(
            experiment_slug="alerter-broker-down",
            host_g_node_alias="d1.alerts",
            start_unix_ms=stamp_ms(lines[0]),
            end_unix_ms=stamp_ms(lines[-1]),
            code_ref="gridworks-alerter jm/gw-alert working tree (the prober, uncommitted at run time); run.sh",
            verdict=verdict,
            claim=CLAIM,
        ),
    )


if __name__ == "__main__":
    main(
        Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "evidence/2026-10-07",
        GwExperimentVerdict(sys.argv[2]) if len(sys.argv) > 2 else GwExperimentVerdict.Pass,
    )
