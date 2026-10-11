"""Display CSVs for the prod-broker outage drill (gitignored, regenerated).

    uv run python views.py alerts      # alerts-display.csv, from instances/
    uv run python views.py reconnects  # reconnects-display.csv, from evidence/

`alerts` decodes each `gw.alert` instance through the codec: one row per
transition, with its time after the broker's listeners stopped.

`reconnects` joins the broker log's accept lines with the connection
lists taken after the fleet was back: one row per accept after the
listeners started, with the login (certificate CN, or the password login)
and whether the connection was still held afterwards. AMQP accepts are
matched to their login by the broker's `connected_at` millisecond; an
accept that matches no held connection is a probe that hung up (the
prober's checks from the alerts box).
"""

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from pydantic import TypeAdapter  # noqa: E402

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.property_format import NonEmptyString, UTCMilliseconds  # noqa: E402
from gwexp.sema.types import GwAlert  # noqa: E402

EVIDENCE = HERE / "evidence"
INSTANCES = HERE / "instances"
LOG = EVIDENCE / "broker-log-reduced.txt"

_UTC_MS = TypeAdapter(UTCMilliseconds)
_NON_EMPTY = TypeAdapter(NonEmptyString)


class Reconnect(NamedTuple):
    """One connection the broker accepted after its listeners started.
    Analysis-internal: no sema word covers a broker-side connection
    accept yet (a `gw.broker.connection` word would retire this);
    `gridworks.event.comm.mqtt.connect` is the client's own view."""

    protocol: NonEmptyString  # "amqp" or "mqtt"
    port: int
    accepted_unix_ms: UTCMilliseconds
    client_id: str  # MQTT client id (the client's instance id); "" for AMQP
    login: str  # certificate CN or password login; "" for a probe that hung up
    held: bool  # still in the after-list, i.e. not a probe


def log_ms(line: str) -> UTCMilliseconds:
    stamp = datetime.fromisoformat(line.split(" [")[0].replace(" ", "T"))
    return _UTC_MS.validate_python(int(stamp.timestamp() * 1000))


def log_lines(marker: str) -> list[str]:
    return [
        ln
        for ln in LOG.read_text().splitlines()
        if marker in ln and not ln.startswith("#")
    ]


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%H:%M:%S.%f")[:-3]


def tsv_rows(name: str) -> list[dict[str, str]]:
    with (EVIDENCE / name).open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def reconnects(start_ms: int) -> list[Reconnect]:
    amqp_login = {
        int(r["connected_at"]): r["user"] for r in tsv_rows("amqp-connections-after.tsv")
    }
    mqtt_login = {
        r["client_id"]: r["user"] for r in tsv_rows("mqtt-connections-after.tsv")
    }
    out: list[Reconnect] = []
    for ln in log_lines("accepting AMQP connection"):
        ms = log_ms(ln)
        if ms < start_ms:
            continue
        login = amqp_login.get(ms, "")
        port = int(ln.rsplit(":", 1)[1])
        out.append(
            Reconnect(_NON_EMPTY.validate_python("amqp"), port, ms, "", login, bool(login))
        )
    for ln in log_lines("Accepted MQTT connection"):
        ms = log_ms(ln)
        if ms < start_ms:
            continue
        client_id = ln.rsplit("client ID ", 1)[1]
        login = mqtt_login.get(client_id, "")
        port = int(ln.split(" for client ID")[0].rsplit(":", 1)[1])
        out.append(
            Reconnect(
                _NON_EMPTY.validate_python("mqtt"), port, ms, client_id, login, bool(login)
            )
        )
    return sorted(out, key=lambda r: r.accepted_unix_ms)


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(path)


def main() -> None:
    view = sys.argv[1] if len(sys.argv) > 1 else ""
    stop_ms = log_ms(log_lines("stopped TLS (SSL) listener")[0])
    start_ms = log_ms(log_lines("Server startup complete")[0])
    if view == "alerts":
        alerts = [
            default_codec.from_dict(json.loads(p.read_text()), expect=GwAlert)
            for p in sorted(INSTANCES.glob("*-gw.alert-000.json"))
        ]
        rows: list[list[object]] = []
        for a in alerts:
            at = a.resolved_ms if a.resolved_ms is not None else a.raised_ms
            rows.append(
                [a.subject, a.kind.value, a.state.value, iso(at), round((at - stop_ms) / 1000, 1)]
            )
        write_csv(
            HERE / "alerts-display.csv",
            ["subject", "kind", "state", "at_utc", "s_after_listeners_stopped"],
            rows,
        )
    elif view == "reconnects":
        write_csv(
            HERE / "reconnects-display.csv",
            ["protocol", "port", "accepted_utc", "s_after_startup", "client_id", "login", "held"],
            [
                [r.protocol, r.port, iso(r.accepted_unix_ms),
                 round((r.accepted_unix_ms - start_ms) / 1000, 1),
                 r.client_id, r.login, r.held]
                for r in reconnects(start_ms)
            ],
        )
    else:
        sys.exit("usage: views.py alerts|reconnects")


if __name__ == "__main__":
    main()
