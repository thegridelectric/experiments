"""Sim-time experiment harness.

Stands up, against the REAL dev-rabbit broker (MQTT plugin, :1885), the
receiving + recording half of the simulated-test-environment "first live
bridge run":

  - a generic broker OBSERVER/recorder (experimentation-tools tool 3):
    binds MQTT `#`, records every message by topic + rx wall-clock +
    parse-outcome to a JSONL logbook, no DB;
  - the real scada-side SimTimeListener (gw_spaceheat/sim_time.py) as the
    SCADA receiver;
  - a second SimTimeListener as the LTN receiver (the LTN has no native
    sim-time listener yet — open item in the sim-time spoke; we reuse the
    proven bridge listener to witness "both receive");
  - on each received timestep, each side publishes a ping/ack back
    (the bridge's "timestep triggers ping/ack both directions" intent),
    so the logbook shows genuine back-and-forth, not just broadcasts.

The publisher (the time coordinator) is the real `tc-hello` from
gridworks-timecoordinator, run separately against the same broker; its
AMQP broadcasts cross to MQTT via the gwbase topology binding
TimeCoordinator-publish -> amq.topic (`rjb.#`).

Run: <scada-venv>/bin/python harness.py --seconds 40 --outdir <dir>
with PYTHONPATH including gridworks-scada/gw_spaceheat.
"""

import argparse
import datetime
import json
import logging
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from gwproactor.config import MQTTClient

from sim_time import SimTimeListener, sim_timestep_mqtt_topic, DEFAULT_TIME_COORDINATOR_ALIAS

RABBIT_MQTT_HOST = "localhost"
RABBIT_MQTT_PORT = 1885


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ts_ms: int) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000).isoformat(timespec="milliseconds")


class Logbook:
    """Thread-safe JSONL append + in-memory tally."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh = path.open("w")
        self._lock = threading.Lock()
        self.count = 0
        self.by_topic: dict[str, int] = {}

    def record(self, **rec) -> None:
        with self._lock:
            self._fh.write(json.dumps(rec) + "\n")
            self._fh.flush()
            self.count += 1
            self.by_topic[rec.get("topic", "?")] = self.by_topic.get(rec.get("topic", "?"), 0) + 1

    def close(self) -> None:
        self._fh.close()


def make_config() -> MQTTClient:
    cfg = MQTTClient(host=RABBIT_MQTT_HOST, port=RABBIT_MQTT_PORT)
    cfg.tls.use_tls = False
    return cfg


class Observer:
    """Generic broker tap: bind MQTT `#`, record every message."""

    def __init__(self, logbook: Logbook, logger: logging.Logger) -> None:
        self._logbook = logbook
        self._logger = logger
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, *_a) -> None:
        client.subscribe("#")
        self._logger.info("observer bound MQTT '#'")

    def _on_message(self, _c, _u, msg: mqtt.MQTTMessage) -> None:
        raw = msg.payload
        try:
            text = raw.decode()
            parsed = json.loads(text)
            outcome = "PARSED" if isinstance(parsed, dict) else "PARSED-NONOBJ"
            type_name = parsed.get("TypeName") if isinstance(parsed, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            text = raw.hex()
            type_name = None
            outcome = "PARSE-ERR"
        self._logbook.record(
            rx_unix_ms=now_ms(), rx_iso=iso(now_ms()), topic=msg.topic,
            qos=int(msg.qos), type_name=type_name, parse_outcome=outcome,
            payload=text,
        )
        self._logger.info("observer rx %-45s type=%s", msg.topic, type_name)

    def start(self) -> None:
        self._client.connect_async(RABBIT_MQTT_HOST, RABBIT_MQTT_PORT, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:
            pass


class Side:
    """One receiver (scada or ltn): a real SimTimeListener that pings back
    on each timestep so the broker shows two-way traffic."""

    def __init__(self, name: str, peer: str, logger: logging.Logger) -> None:
        self.name = name
        self.peer = peer
        self.logger = logger
        self.receipts: list[dict] = []
        # a tiny publisher client for the ping/ack back to the broker
        self._pub = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._pub.connect_async(RABBIT_MQTT_HOST, RABBIT_MQTT_PORT, keepalive=30)
        self._pub.loop_start()
        self.listener = SimTimeListener(
            config=make_config(), on_timestep=self._on_timestep,
            logger=logger.getChild(f"{name}.listener"),
        )

    def _on_timestep(self, t: int) -> None:
        rec = {"who": self.name, "sim_time_unix_s": t, "rx_unix_ms": now_ms()}
        self.receipts.append(rec)
        self.logger.info("%s RECEIVED sim.timestep TimeUnixS=%s", self.name.upper(), t)
        topic = f"gw/sim-experiment/{self.name}/to/{self.peer}/sim-ack"
        payload = json.dumps({
            "TypeName": "sim.ack", "From": self.name, "To": self.peer,
            "AckSimTimeUnixS": t, "SentUnixMs": now_ms(),
        })
        self._pub.publish(topic, payload)

    def start(self) -> None:
        self.listener.start()

    def stop(self) -> None:
        self.listener.stop()
        self._pub.loop_stop()
        try:
            self._pub.disconnect()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--outdir", default="/Users/jessica/GridWorks/sim-time-experiment/out")
    ap.add_argument("--tc-alias", default=DEFAULT_TIME_COORDINATOR_ALIAS)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(outdir / "harness.log", mode="w")],
    )
    log = logging.getLogger("sim-exp")
    log.info("sim-time topic = %s", sim_timestep_mqtt_topic(args.tc_alias))

    logbook = Logbook(outdir / "messages.jsonl")
    observer = Observer(logbook, log.getChild("observer"))
    scada = Side("scada", "ltn", log)
    ltn = Side("ltn", "scada", log)

    observer.start()
    scada.start()
    ltn.start()
    log.info("observer + scada + ltn up; recording for %.0fs (start tc-hello now)", args.seconds)

    t_end = time.time() + args.seconds
    while time.time() < t_end:
        time.sleep(0.5)

    scada.stop(); ltn.stop(); observer.stop(); logbook.close()

    summary = {
        "broker": f"{RABBIT_MQTT_HOST}:{RABBIT_MQTT_PORT} (dev-rabbit MQTT plugin)",
        "sim_timestep_topic": sim_timestep_mqtt_topic(args.tc_alias),
        "total_messages_recorded": logbook.count,
        "messages_by_topic": logbook.by_topic,
        "scada_timesteps_received": len(scada.receipts),
        "ltn_timesteps_received": len(ltn.receipts),
        "scada_receipts": scada.receipts,
        "ltn_receipts": ltn.receipts,
        "both_received": len(scada.receipts) > 0 and len(ltn.receipts) > 0,
    }
    (outdir / "receipts.json").write_text(json.dumps(summary, indent=2))
    log.info("DONE. recorded=%d scada=%d ltn=%d both_received=%s",
             logbook.count, len(scada.receipts), len(ltn.receipts), summary["both_received"])
    print(json.dumps({k: summary[k] for k in
                      ("total_messages_recorded", "messages_by_topic",
                       "scada_timesteps_received", "ltn_timesteps_received",
                       "both_received")}, indent=2))


if __name__ == "__main__":
    main()
