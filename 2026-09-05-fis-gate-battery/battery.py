"""The FIS gate battery: every done-when verdict, against the rig named by
the environment (local harness broker by default; `remote.env` for a box).

Every done-when verdict of the stand-up-fis design, witnessed twice: by the
client's connect outcome against the real broker + mechanism + FIS, and by
the `auth_events` row FIS recorded for that verdict. The AMQP legs speak
through gwbase's own credentials class and claims word; the MQTT legs are a
plain paho client with a cert, the shape a scada presents.

The rig (`rig.py`) owns FIS, so one case (kill unconfirmable) can restart it
with a wrong management password. Run through ./run.sh (or ./run-remote.sh),
or directly:

    uv run --project ../../gridworks-fleet-index-service \
        --with pika --with paho-mqtt --with ../../gridworks-base battery.py
"""

import argparse
import json
import ssl
import sys
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
import pika
import pika.exceptions
import psycopg
from gwbase.credentials import GridworksClaimsCredentials
from gwbase.sema.types import FisConnectClaims
from gwbase.transport_encoding import RoutingClass, json_broadcast_routing_key

from rig import Rig, rig_from_env

HERE = Path(__file__).parent
RIG: Rig  # set in main(); the broker, the identities, the FIS and broker levers

results: list[tuple[str, bool, str]] = []
log_lines: list[str] = []


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    log_lines.append(line)


def case(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


# --- FIS process -----------------------------------------------------------


# --- witnesses -------------------------------------------------------------


def last_event(principal: str, instance: str) -> tuple[str, str] | None:
    """FIS's own record of the verdict; the write is a background task, so
    poll briefly."""
    for _ in range(20):
        with psycopg.connect(RIG.db_url) as conn:
            row = conn.execute(
                "select decision, reason from auth_events where principal_id=%s "
                "and instance_id=%s order by decided_at_unix_ms desc limit 1",
                (principal, instance),
            ).fetchone()
        if row is not None:
            return row
        time.sleep(0.1)
    return None


def event_is(principal: str, instance: str, decision: str, reason: str) -> tuple[bool, str]:
    got = last_event(principal, instance)
    want = (decision, reason)
    return got == want, f"auth_events={got} want={want}"


def wait_connections(principal: str, want: int, within_s: float = 5.0) -> set[str]:
    deadline = time.perf_counter() + within_s
    while True:
        live = RIG.live_connections(principal)
        if len(live) == want or time.perf_counter() >= deadline:
            return live
        time.sleep(0.05)


# --- AMQP leg --------------------------------------------------------------


def ssl_ctx(name: str | None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(RIG.ca)
    if name is not None:
        ctx.load_cert_chain(*RIG.cert(name))
    return ctx


def amqp_connect(
    name: str | None, claims: FisConnectClaims, vhost: str | None = None
) -> tuple[str, pika.BlockingConnection | None, float]:
    """Outcome tag, the open connection (on allow), and the connect time."""
    params = pika.ConnectionParameters(
        host=RIG.broker_host,
        port=RIG.amqps_port,
        virtual_host=RIG.run if vhost is None else vhost,
        ssl_options=pika.SSLOptions(ssl_ctx(name), server_hostname=RIG.broker_host),
        credentials=GridworksClaimsCredentials(claims),
        connection_attempts=1,
        socket_timeout=15,
    )
    t0 = time.perf_counter()
    try:
        conn = pika.BlockingConnection(params)
        return "allow", conn, time.perf_counter() - t0
    except pika.exceptions.ProbableAuthenticationError:
        return "deny-user", None, time.perf_counter() - t0
    except pika.exceptions.ProbableAccessDeniedError:
        return "deny-vhost", None, time.perf_counter() - t0
    except (pika.exceptions.AMQPConnectionError, ssl.SSLError, OSError) as e:
        return f"error:{type(e).__name__}:{e}"[:160], None, time.perf_counter() - t0


def weather_claims(instance: str, alias: str | None = None, cls: str | None = None, run: str | None = None) -> FisConnectClaims:
    return FisConnectClaims(
        alias=RIG.weather_alias if alias is None else alias,
        instance_id=instance,
        run=RIG.run if run is None else run,
        g_node_class=RIG.weather_class if cls is None else cls,
    )


def closed_by_broker(conn: pika.BlockingConnection, within_s: float) -> float | None:
    """Seconds until the broker closed this connection, or None if it is
    still open after `within_s`."""
    t0 = time.perf_counter()
    try:
        conn.process_data_events(time_limit=within_s)
    except (pika.exceptions.ConnectionClosedByBroker, pika.exceptions.StreamLostError):
        return time.perf_counter() - t0
    return None if conn.is_open else time.perf_counter() - t0


def publish_outcome(conn: pika.BlockingConnection, exchange: str, routing_key: str, user_id: str | None) -> str:
    """'ok' when the channel survives the publish; otherwise `closed <code>`
    with the broker's reply code (403 for a topic verdict, 406 for a bad
    user_id). A BlockingChannel surfaces a broker close as an exception on
    the next process step, so drive the loop in small slices and catch it."""
    ch = conn.channel()
    try:
        ch.basic_publish(exchange, routing_key, b"{}", properties=pika.BasicProperties(user_id=user_id))
        for _ in range(20):
            conn.process_data_events(time_limit=0.1)
            if not ch.is_open:
                break
    except pika.exceptions.ChannelClosedByBroker as e:
        return f"closed {e.reply_code}"
    except pika.exceptions.ConnectionClosedByBroker as e:
        return f"closed {e.reply_code}"
    if not ch.is_open:
        reason = getattr(ch, "_closing_reason", None)
        return f"closed {getattr(reason, 'reply_code', '?')}"
    ch.close()
    return "ok"


def weather_key(from_alias: str) -> str:
    return json_broadcast_routing_key(
        from_alias=from_alias,
        from_class_token=RoutingClass.WeatherForecastService.value,
        type_name="weather.forecast",
    )


def ltn_claims(instance: str) -> FisConnectClaims:
    return FisConnectClaims(alias=RIG.ltn_alias, instance_id=instance, run=RIG.run, g_node_class="LeafTransactiveNode")


def ltn_key(from_alias: str) -> str:
    return json_broadcast_routing_key(
        from_alias=from_alias,
        from_class_token=RoutingClass.LeafTransactiveNode.value,
        type_name="gt.sh.status",
    )


# --- MQTT leg --------------------------------------------------------------


class MqttProbe:
    def __init__(self, name: str, client_id: str) -> None:
        self.connected = threading.Event()
        self.rc: str | None = None
        self.disconnected = threading.Event()
        self.subscribed = threading.Event()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv311
        )
        cert, key = RIG.cert(name)
        self.client.tls_set(ca_certs=RIG.ca, certfile=cert, keyfile=key)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_subscribe = lambda *_: self.subscribed.set()

    def _on_connect(self, _c, _u, _f, reason_code, _p=None) -> None:
        self.rc = str(reason_code)
        self.connected.set()

    def _on_disconnect(self, *_args) -> None:
        self.disconnected.set()

    def connect(self) -> str:
        try:
            self.client.connect(RIG.broker_host, RIG.mqtts_port, keepalive=30)
        except (OSError, ssl.SSLError) as e:
            return f"error:{type(e).__name__}"
        self.client.loop_start()
        if not self.connected.wait(5):
            self.client.loop_stop()
            return "refused" if self.disconnected.is_set() else "timeout"
        return "allow" if self.rc == "Success" else f"refused:{self.rc}"

    def publish_outcome(self, topic: str) -> str:
        self.disconnected.clear()
        self.client.publish(topic, "{}", qos=0)
        return "disconnected" if self.disconnected.wait(2) else "ok"

    def subscribe_outcome(self, topic: str) -> str:
        self.client.subscribe(topic, qos=0)
        return "granted" if self.subscribed.wait(3) else "no-suback"

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


# --- the battery -----------------------------------------------------------


def run_battery() -> None:
    ids = RIG.ids
    weather = ids["weather"]
    scada = ids["scada"]

    # 0. no client cert → refused at the TLS layer, before any claim is heard
    tag, _, _ = amqp_connect(None, weather_claims(str(uuid.uuid4())))
    case("no_cert_tls_refused", tag.startswith("error"), tag)

    # 1. unknown principal (a cert the CA signed, never minted) → deny
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("unknown", FisConnectClaims(alias=RIG.alias("nobody"), instance_id=inst, run=RIG.run))
    ok, d = event_is(ids["unknown"], inst, "Denied", "PrincipalNotFound")
    case("unknown_principal_deny", tag == "deny-user" and ok, f"{tag}; {d}")

    # 2. honest weather GNode, instance A → allow (supersession of nothing)
    inst_a = str(uuid.uuid4())
    tag, conn_a, dt = amqp_connect("weather", weather_claims(inst_a))
    ok, d = event_is(weather, inst_a, "Authorized", "Superseded")
    case("weather_first_connect_allow", tag == "allow" and ok, f"{tag} in {dt:.2f}s; {d}")

    # 3. same instance again → idempotent reconnect, A survives
    tag, conn_a2, _ = amqp_connect("weather", weather_claims(inst_a))
    ok, d = event_is(weather, inst_a, "Authorized", "IdempotentReconnect")
    a_still_open = conn_a is not None and closed_by_broker(conn_a, 1.0) is None
    case("same_instance_idempotent", tag == "allow" and ok and a_still_open, f"{tag}; A open={a_still_open}; {d}")
    if conn_a2 is not None:
        conn_a2.close()

    # 4. racing second instance B → ordered supersession: A closed, then B in.
    # The broker's own connection list is the oracle: because the kill
    # confirms empty before allowing, exactly one weather connection (B) is
    # live the instant B is admitted, and A's connection is gone.
    a_names = RIG.live_connections(weather)
    inst_b = str(uuid.uuid4())
    tag, conn_b, dt = amqp_connect("weather", weather_claims(inst_b))
    ok, d = event_is(weather, inst_b, "Authorized", "Superseded")
    live = RIG.live_connections(weather)
    a_gone = a_names.isdisjoint(live)
    case(
        "supersession_predecessor_closed",
        tag == "allow" and ok and a_gone and len(live) == 1,
        f"B {tag} in {dt:.2f}s; A gone={a_gone}; weather live now={len(live)}; {d}",
    )

    # 5. the revoked instance A tries again → denied, forever
    tag, _, _ = amqp_connect("weather", weather_claims(inst_a))
    ok, d = event_is(weather, inst_a, "Denied", "InstanceRevoked")
    case("revoked_instance_deny", tag == "deny-user" and ok, f"{tag}; {d}")

    # 6. wrong alias claim / wrong class claim → deny; B untouched
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("weather", weather_claims(inst, alias=RIG.stale_alias))
    ok, d = event_is(weather, inst, "Denied", "AliasMismatch")
    case("wrong_alias_claim_deny", tag == "deny-user" and ok, f"{tag}; {d}")
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("weather", weather_claims(inst, cls="PriceForecastService"))
    ok, d = event_is(weather, inst, "Denied", "ClassMismatch")
    case("wrong_class_claim_deny", tag == "deny-user" and ok, f"{tag}; {d}")

    # 7. run claim ≠ vhost. The executor's rule ("an Active lease for
    # (principal, vhost) exists iff the claimed run equals the vhost") is
    # witnessed on a principal with no lease on this vhost: /auth/user leases
    # the other run, /auth/vhost for this one finds nothing and denies.
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("service1", FisConnectClaims(alias=RIG.alias("battery.other"), instance_id=inst, run=RIG.other_run), vhost=RIG.run)
    ev = last_event(ids["service1"], inst)
    user_leased = ev is not None and ev[0] == "Authorized"
    case("run_claim_vs_vhost_deny_fresh_principal", tag == "deny-vhost" and user_leased, f"{tag}; user-verdict={ev}")
    # The same mismatch by a principal that ALREADY holds a live lease on the
    # opened vhost (weather's B on this run). Finding B: /auth/vhost carries no
    # claims, so a lease lookup admitted this; the claimed run now rides the
    # connection's user tag (`allow <run>` at /auth/user) and the vhost check
    # compares that tag, so the live lease changes nothing.
    inst = str(uuid.uuid4())
    tag, conn_gap, _ = amqp_connect("weather", weather_claims(inst, run=RIG.other_run), vhost=RIG.run)
    case("run_claim_vs_vhost_deny_with_live_lease", tag == "deny-vhost", f"{tag} (weather live on {RIG.run} while this connection claimed {RIG.other_run})")
    if conn_gap is not None:
        conn_gap.close()
    # KNOWN LIMIT (not scored): the supersession kill is close-by-username,
    # broker-wide for the identity, so the other-run attempt above also closed
    # weather's connection B on this run. Exact while a broker hosts one run
    # (the staging and prod posture); the dev broker hosts d1__1 and d1__2. A
    # vhost-scoped kill would read the tracking table's vhost per connection.
    b_closed = conn_b is not None and closed_by_broker(conn_b, 2.0) is not None
    log(f"KNOWN-LIMIT broker_wide_kill_closed_other_run: B closed={b_closed}")
    wait_connections(weather, 0)
    inst_b = str(uuid.uuid4())
    tag, conn_b, _ = amqp_connect("weather", weather_claims(inst_b))
    log(f"reopened B as a fresh instance: {tag}")
    # a run outside this FIS's universe never even reaches a lease
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("weather", weather_claims(inst, run=RIG.foreign_run), vhost=RIG.run)
    ok, d = event_is(weather, inst, "Denied", "RunOutsideUniverse")
    case("run_outside_universe_deny", tag == "deny-user" and ok, f"{tag}; {d}")

    # 8. suspended principal → deny; lifted → the same instance is admitted
    RIG.principal_status(weather, "suspend")
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("weather", weather_claims(inst))
    ok, d = event_is(weather, inst, "Denied", "PrincipalSuspended")
    case("suspended_principal_deny", tag == "deny-user" and ok, f"{tag}; {d}")
    RIG.principal_status(weather, "activate")
    b_still_open = conn_b is not None and conn_b.is_open and closed_by_broker(conn_b, 0.5) is None
    case("suspension_does_not_kill_live_lease", b_still_open, f"B open={b_still_open} (eviction = suspend + kill, separately)")

    # 9. topic write pinned to the alias, on a fresh beech-LTN identity (its
    # first connect is an empty kill, so this is deterministic even while the
    # supersession finding stands). A GNode with a registry alias: own-alias
    # writes pass, a stale-alias write is denied 403 at /auth/topic.
    ltn = ids["ltn"]
    inst = str(uuid.uuid4())
    tag, conn_l, _ = amqp_connect("ltn", ltn_claims(inst))
    ok, d = event_is(ltn, inst, "Authorized", "Superseded")
    case("ltn_first_connect_allow", tag == "allow" and ok, f"{tag}; {d}")
    if conn_l is not None:
        o1 = publish_outcome(conn_l, "ltnmic_tx", ltn_key(RIG.ltn_alias), None)
        o2 = publish_outcome(conn_l, "ltnmic_tx", ltn_key(RIG.stale_alias), None)
        case("topic_write_own_alias_ok", o1 == "ok", o1)
        case("topic_write_stale_alias_denied", o2 == "closed 403", o2)
        conn_l.close()

    # 10. a service principal (fresh connect): no registry alias, claims carry
    # no class; its writes are allowed (cert-authenticated infra). user_id is
    # validated by the broker itself — own id passes, a forged id is refused
    # 406. Each leg is its own service identity, so nothing supersedes.
    inst = str(uuid.uuid4())
    tap = RIG.alias("battery.tap")
    tag, conn_s, _ = amqp_connect("service0", FisConnectClaims(alias=tap, instance_id=inst, run=RIG.run))
    ok, d = event_is(ids["service0"], inst, "Authorized", "Superseded")
    case("service_principal_allow", tag == "allow" and ok, f"{tag}; {d}")
    if conn_s is not None:
        case("service_topic_write_allowed", publish_outcome(conn_s, "ltnmic_tx", ltn_key(tap), None) == "ok", "own claimed alias")
        case("user_id_own_identity_ok", publish_outcome(conn_s, "ltnmic_tx", ltn_key(tap), ids["service0"]) == "ok", "user_id = self")
        conn_s.close()
    inst = str(uuid.uuid4())
    two = RIG.alias("battery.two")
    _, conn_f, _ = amqp_connect("service1", FisConnectClaims(alias=two, instance_id=inst, run=RIG.run))
    if conn_f is not None:
        o = publish_outcome(conn_f, "ltnmic_tx", ltn_key(two), "someone-else")
        case("user_id_forged_refused_by_broker", o == "closed 406", o)
        try:
            if conn_f.is_open:
                conn_f.close()
        except pika.exceptions.ConnectionClosedByBroker:
            pass

    # 11. management API unreachable → supersession unconfirmable → deny
    RIG.fis_stop()
    RIG.fis_start(FIS_RABBIT_MGMT_PASSWORD="wrong")
    inst = str(uuid.uuid4())
    tag, _, _ = amqp_connect("weather", weather_claims(inst))
    ok, d = event_is(weather, inst, "Denied", "KillUnconfirmed")
    case("kill_unconfirmed_fail_closed", tag == "deny-user" and ok, f"{tag}; {d}")
    RIG.fis_stop()
    RIG.fis_start()

    # 12. clean restart: with nothing to kill, a successor is admitted at once.
    if conn_b is not None and conn_b.is_open:
        conn_b.close()
    wait_connections(weather, 0)
    time.sleep(0.5)
    inst = str(uuid.uuid4())
    tag, conn_c, dt = amqp_connect("weather", weather_claims(inst))
    ok, d = event_is(weather, inst, "Authorized", "Superseded")
    case("clean_restart_admitted_fast", tag == "allow" and ok and dt < 1.0, f"{tag} in {dt:.3f}s; {d}")
    if conn_c is not None:
        conn_c.close()

    # 13. MQTT: the scada shape — cert identity, client_id = instance id
    inst = str(uuid.uuid4())
    p = MqttProbe("scada", inst)
    tag = p.connect()
    ok, d = event_is(scada, inst, "Authorized", "Superseded")
    case("mqtt_scada_connect_allow", tag == "allow" and ok, f"{tag}; {d}")
    if tag == "allow":
        case("mqtt_subscribe_read_allowed", p.subscribe_outcome("gw/#") == "granted", "suback")
        o1 = p.publish_outcome(f"gw/{RIG.scada_alias.replace('.', '-')}/status")
        case("mqtt_publish_own_alias_ok", o1 == "ok", o1)
        o2 = p.publish_outcome(f"gw/{RIG.stale_alias.replace('.', '-')}/status")
        case("mqtt_publish_stale_alias_disconnected", o2 == "disconnected", o2)
        p.close()
    p2 = MqttProbe("scada", "not-a-uuid")
    tag = p2.connect()
    case("mqtt_client_id_not_uuid_refused", tag != "allow", tag)
    p2.close() if tag == "allow" else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=str(HERE / "runs" / time.strftime("%Y%m%dT%H%M", time.gmtime())))
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    global RIG
    RIG = rig_from_env(run_dir)
    RIG.fis_stop()
    RIG.reset_lease_state()
    RIG.fis_start()
    log(f"FIS up on {RIG.broker_host}; universe {RIG.universe}; mirror seeded from the registry — see {RIG.fis_log_path}")
    try:
        run_battery()
    finally:
        RIG.close()
    passed = sum(1 for _, ok, _ in results if ok)
    log(f"{passed}/{len(results)} cases pass")
    (run_dir / "battery.log").write_text("\n".join(log_lines) + "\n")
    (run_dir / "battery.json").write_text(json.dumps([{"case": n, "pass": ok, "detail": d} for n, ok, d in results], indent=1))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
