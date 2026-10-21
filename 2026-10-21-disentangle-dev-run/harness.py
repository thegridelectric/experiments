#!/usr/bin/env python3
"""The unattended steps of the OPS-473 dev run: the layout path from the dev
broker to the dashboard's summaries, the operating-status path, the replay
guard, and the no-person sweep.

The harness acts as cedar's scada on the dev broker: it publishes a
`layout.lite` 012 and a `gw.house.operating.status` 000 inside a `gw`
envelope with the scada's routing keys (captured from the sim scada's
traffic), then reads what journalkeeper projected and decodes what the API
serves as `gw.house.summary`. The sim scada on `jm/spruce-unlimbo` sends
layout.lite 013, which journalkeeper's snapshot decodes as degraded, so the
012 publish is how the layouts row is exercised here; that gap is a finding
of the run, recorded in the README.

Run from the experiments folder::

    uv run python 2026-10-21-disentangle-dev-run/harness.py \\
        --db-url "$DEVRUN_DB_URL" --api-base http://127.0.0.1:8000 \\
        --out 2026-10-21-disentangle-dev-run/logs/harness.json

The database URL is the local dev journal DB's (`GJK_DB_URL` in
`gridworks-journalkeeper/.env`, psycopg form). The broker URL
(`GWEXP_RABBIT__URL`) and the API login the run created
(`DEVRUN_API_USER`, `DEVRUN_API_PASSWORD`) come from `experiments/.env`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Literal, NamedTuple, TypeVar

import pika
import psycopg
from psycopg import sql
from gwexp.sema.codec import SemaCodec
from gwexp.sema.enums import (
    GwExperimentVerdict,
    GwStandbyPosture,
    GwTopState,
    Gw1SeasonalStorageMode,
    Gw1ServiceMode,
    Gw1SystemMode,
    TaValidationState,
)
from gwexp.sema.property_format import UTCMilliseconds, UTCSeconds
from gwexp.sema.types import GwHouseOperatingStatus, GwHouseSummary
from gwexp.sema.types.gridworks_header import GridworksHeader
from gwexp.sema.types.gw import Gw, Payload
from gwexp.sema.types.old_versions.layout_lite_012 import LayoutLite012
from pydantic import TypeAdapter

HERE = Path(__file__).resolve().parent
ENV = HERE.parent / ".env"
SAMPLE_012 = HERE.parent / "src" / "gwexp" / "sema" / "samples" / "layout.lite.012.json"

HOUSE = "d1.isone.me.versant.keene.cedar"
SCADA = HOUSE + ".scada"
TA = HOUSE + ".ta"
# What step 2 put in the private store and nothing else may hold.
PERSON = ("Quillon", "Farrowby", "418 Larkspur Hollow Rd", "larkspur-hollow-devrun")

CODEC = SemaCodec()
MS = TypeAdapter(UTCMilliseconds)
SECONDS = TypeAdapter(UTCSeconds)
T = TypeVar("T")


class Check(NamedTuple):
    """One assertion of the run: its step, what was expected, what was seen.

    No sema word covers an experiment check yet; a `gw.experiment.check`
    word retires this record.
    """

    step: str
    name: str
    passed: bool
    detail: str


def env_value(key: str) -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{key} not found in experiments/.env")


def now_ms() -> UTCMilliseconds:
    return MS.validate_python(int(time.time() * 1000))


def routing_key(message_type: str, dst: str = "ltn") -> str:
    return f"gw.{SCADA.replace('.', '-')}.to.{dst}.{message_type.replace('.', '-')}"


def publish(amqp_url: str, payload: LayoutLite012 | GwHouseOperatingStatus, message_id: str) -> None:
    """Send the payload in the scada's `gw` envelope on its routing key."""
    envelope = Gw(
        header=GridworksHeader(
            src=SCADA,
            dst="ltn",
            message_type=payload.type_name,
            message_id=message_id,
            ack_required=False,
        ),
        payload=Payload.model_validate(payload.to_dict()),
    )
    conn = pika.BlockingConnection(pika.URLParameters(amqp_url))
    try:
        ch = conn.channel()
        ch.basic_publish(exchange="amq.topic", routing_key=routing_key(payload.type_name), body=envelope.to_bytes())
    finally:
        conn.close()


def layout_012(system_mode: Gw1SystemMode, created_ms: UTCMilliseconds) -> LayoutLite012:
    d = CODEC.from_dict(json.loads(SAMPLE_012.read_text()), auto_upgrade=False, expect=LayoutLite012).to_dict()
    d["FromGNodeAlias"] = SCADA
    d["SystemMode"] = system_mode.value
    d["MessageCreatedMs"] = created_ms
    d["MessageId"] = str(uuid.uuid4())
    return LayoutLite012.from_dict(d)


def operating_status(created_ms: UTCMilliseconds) -> GwHouseOperatingStatus:
    return GwHouseOperatingStatus(
        scada_alias=SCADA,
        validation_state=TaValidationState.ValidatedSimulatedAsset,
        standby=False,
        standby_posture=GwStandbyPosture.NoHeatingOrCooling,
        seasonal_storage_mode=Gw1SeasonalStorageMode.BufferOnly,
        service_mode=Gw1ServiceMode.Heating,
        accepts_dispatch=True,
        top_state=GwTopState.Auto,
        scada_blind=False,
        ltn_dispatching=True,
        created_ms=created_ms,
    )


class Api:
    def __init__(self, base: str):
        self.base = base

    def token(self) -> str:
        data = urllib.parse.urlencode(
            {"username": env_value("DEVRUN_API_USER"), "password": env_value("DEVRUN_API_PASSWORD")}
        ).encode()
        req = urllib.request.Request(f"{self.base}/api/v2/sessions", data=data, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            # The OAuth2 password-flow response, outside sema.
            return json.load(r)["access_token"]

    def summaries_text(self) -> str:
        req = urllib.request.Request(f"{self.base}/api/v2/installations/*/summaries",
                                     headers={"Authorization": f"Bearer {self.token()}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode()

    def summaries(self) -> list[GwHouseSummary]:
        """Every summary, decoded strictly: a field the word lacks fails the decode."""
        return [CODEC.from_dict(d, expect=GwHouseSummary) for d in json.loads(self.summaries_text())]

    def cedar(self) -> GwHouseSummary | None:
        return next((s for s in self.summaries() if s.g_node_alias == HOUSE), None)


def wait_for(fn: Callable[[], T | Literal[False] | None], seconds: float = 20, every: float = 1.0) -> T | None:
    """Poll fn until it returns a truthy value, or None when the window ends."""
    deadline = time.monotonic() + seconds
    while True:
        value = fn()
        if value:
            return value
        if time.monotonic() > deadline:
            return None
        time.sleep(every)


class Db:
    def __init__(self, url: str):
        self.conn = psycopg.connect(url, autocommit=True)

    def layouts_row(self) -> tuple | None:
        return self.conn.execute(
            "select ta_g_node_id::text, from_alias, version, payload->>'SystemMode', "
            "extract(epoch from sent_at)*1000, message_id::text from gridworks.layouts "
            "where terminal_asset_alias = %s", (TA,)).fetchone()

    def status_row(self) -> tuple | None:
        return self.conn.execute(
            "select ta_g_node_id::text, source, payload->>'TopState', "
            "extract(epoch from created_at)*1000 from gridworks.house_operating_status "
            "where terminal_asset_alias = %s", (TA,)).fetchone()

    def ta_id(self) -> str:
        row = self.conn.execute("select id::text from gridworks.g_nodes where alias = %s", (TA,)).fetchone()
        assert row is not None, f"{TA} is not in gridworks.g_nodes"
        return row[0]

    def message(self, message_id: str) -> tuple | None:
        return self.conn.execute(
            "select message_type_name, from_alias, extract(epoch from timestamp)*1000 "
            "from gridworks.messages where id = %s", (message_id,)).fetchone()

    def person_hits(self) -> list[str]:
        hits = []
        tables = [r[0] for r in self.conn.execute(
            "select tablename from pg_tables where schemaname='gridworks' and tablename <> 'readings'")]
        for t in tables:
            for needle in PERSON:
                query = sql.SQL("select count(*) from gridworks.{t} where {t}::text ilike %s").format(
                    t=sql.Identifier(t))
                row = self.conn.execute(query, (f"%{needle}%",)).fetchone()
                if row and row[0]:
                    hits.append(f"{t}: {needle} x{row[0]}")
        return hits


def status_json(summary: GwHouseSummary | None) -> str:
    status = summary.operating_status if summary else None
    return status.to_bytes().decode() if status else "null"


def run(args: argparse.Namespace) -> list[Check]:
    db = Db(args.db_url)
    api = Api(args.api_base)
    amqp_url = env_value("GWEXP_RABBIT__URL")
    checks: list[Check] = []
    ta_id = db.ta_id()

    # Step 3: the layout path. The sim scada's 013 is degraded in gjk, so
    # the harness sends the 012 the current projection accepts.
    layout = layout_012(Gw1SystemMode.Heating, now_ms())
    publish(amqp_url, layout, layout.message_id)
    row = wait_for(lambda: (r := db.layouts_row()) and r[5] == layout.message_id and r)
    checks.append(Check("3", "layouts row keyed by the registry's TA GNodeId",
                        bool(row) and row[0] == ta_id, f"row={row} ta_id={ta_id}"))
    checks.append(Check("3", "layouts row sent_at is the word's MessageCreatedMs and from_alias the scada",
                        bool(row) and int(row[4]) == layout.message_created_ms and row[1] == SCADA, f"row={row}"))
    msg = db.message(layout.message_id)
    checks.append(Check("3", "the layout.lite is journaled in messages",
                        bool(msg) and msg is not None and msg[0] == "layout.lite", f"messages={msg}"))

    # Step 3, derived status: gjk deduces a row from the layout and the
    # newest snapshot for a house whose scada sends no status word.
    status = wait_for(lambda: (r := db.status_row()) and r)
    checks.append(Check("3", "derived house_operating_status row from layout + snapshot",
                        bool(status) and status[1] == "derived" and status[0] == ta_id, f"status={status}"))

    # Step 4: the summary decodes as gw.house.summary 000, which has no
    # person field, and nests the layout and the derived status.
    summary = wait_for(lambda: (s := api.cedar()) and s.layout and s)
    checks.append(Check("4", "summary: decodes strictly, TaGNodeId is the registry's, Layout 012 present",
                        bool(summary) and summary.ta_g_node_id == ta_id and isinstance(summary.layout, LayoutLite012),
                        summary.model_copy(update={"layout": None}).to_bytes().decode() if summary else "null"))
    checks.append(Check("4", "summary: OperatingStatus nested (derived), word verbatim",
                        bool(summary) and isinstance(summary.operating_status, GwHouseOperatingStatus),
                        status_json(summary)))

    # Step 3, scada status: a status word from the scada takes the row over
    # the derived one, guarded on CreatedMs.
    sent = operating_status(now_ms())
    publish(amqp_url, sent, str(uuid.uuid4()))
    status = wait_for(lambda: (r := db.status_row()) and r[1] == "scada" and int(r[3]) == sent.created_ms and r)
    checks.append(Check("3", "scada status word replaces the derived row",
                        bool(status) and status[1] == "scada" and int(status[3]) == sent.created_ms, f"status={status}"))
    summary = wait_for(lambda: (s := api.cedar()) and s.operating_status
                       and s.operating_status.created_ms == sent.created_ms and s)
    checks.append(Check("4", "summary: OperatingStatus is the scada's word, CreatedMs intact",
                        bool(summary), status_json(summary)))
    older = operating_status(MS.validate_python(sent.created_ms - 60_000))
    publish(amqp_url, older, str(uuid.uuid4()))
    time.sleep(3)
    status = db.status_row()
    checks.append(Check("3", "an older status word does not regress the row",
                        bool(status) and status is not None and int(status[3]) == sent.created_ms, f"status={status}"))

    # Step 6: a layout change moves the row and the summary.
    changed = layout_012(Gw1SystemMode.Standby, now_ms())
    publish(amqp_url, changed, changed.message_id)
    row = wait_for(lambda: (r := db.layouts_row()) and r[5] == changed.message_id and r)
    checks.append(Check("6", "layout change: row has the new SystemMode and sent_at",
                        bool(row) and row[3] == "Standby" and int(row[4]) == changed.message_created_ms, f"row={row}"))
    summary = wait_for(lambda: (s := api.cedar()) and isinstance(s.layout, LayoutLite012)
                       and s.layout.system_mode == Gw1SystemMode.Standby and s)
    checks.append(Check("6", "summary Layout follows the change", bool(summary),
                        summary.layout.system_mode.value if summary and summary.layout else "null"))

    # Step 7: the replay guard. The step-3 body again, its original stamp.
    publish(amqp_url, layout, layout.message_id)
    time.sleep(3)
    row = db.layouts_row()
    checks.append(Check("7", "replayed older layout leaves the row unchanged",
                        bool(row) and row is not None and row[5] == changed.message_id and row[3] == "Standby",
                        f"row={row}"))

    # Step 10: no person anywhere but the store.
    hits = db.person_hits()
    checks.append(Check("10", "journal DB: no scrambled name or street in any gw_data table", not hits, f"hits={hits}"))
    api_text = api.summaries_text().lower()
    checks.append(Check("10", "API summaries: no scrambled name or street",
                        not any(p.lower() in api_text for p in PERSON), ""))
    capture = sorted((HERE / "captures").glob("broker-capture-*.jsonl"))
    cap_hits = []
    for f in capture:
        text = f.read_text().lower()
        cap_hits += [p for p in PERSON if p.lower() in text]
    checks.append(Check("10", "broker capture: no scrambled name or street on the bus", not cap_hits,
                        f"files={[f.name for f in capture]} hits={cap_hits}"))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", required=True, help="local dev journal DB, psycopg form")
    parser.add_argument("--api-base", required=True, help="local web-backend, e.g. http://127.0.0.1:8000")
    parser.add_argument("--out", type=Path, required=True, help="where the checks are written (JSON)")
    args = parser.parse_args()
    started = SECONDS.validate_python(int(time.time()))
    checks = run(args)
    verdict = GwExperimentVerdict.Pass if all(c.passed for c in checks) else GwExperimentVerdict.Fail
    # Serialization boundary: the record's PascalCase dict form.
    result = {
        "StartedS": started,
        "EndedS": SECONDS.validate_python(int(time.time())),
        "Checks": [{"Step": c.step, "Name": c.name, "Passed": c.passed, "Detail": c.detail} for c in checks],
        "Verdict": verdict.value,
    }
    args.out.write_text(json.dumps(result, indent=1))
    for c in checks:
        print(f"{'PASS' if c.passed else 'FAIL'}  step {c.step}: {c.name}")
    print(verdict.value, f"{sum(c.passed for c in checks)}/{len(checks)}", args.out)
    sys.exit(0 if verdict == GwExperimentVerdict.Pass else 1)


if __name__ == "__main__":
    main()
