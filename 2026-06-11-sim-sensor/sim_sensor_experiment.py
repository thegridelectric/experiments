"""SimSensor experiment — get a SimSensor outputting exactly what we want.

The smallest EDD step toward the simulated test environment (simulated-actors
spoke "DO THIS NEXT"). A thin SimSensor, configured generically from a layout's
sensor channels, publishes a reading per channel on a broker; an independent
observer witnesses them; we verify it emitted EXACTLY the expected channels
with the right units. No scada yet — prove the sensor-output half in isolation.

Run: <scada-venv>/bin/python sim_sensor_experiment.py
"""

import json
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

HOST, PORT = "localhost", 1883  # the "sensor broker"
LAYOUT = "/Users/jessica/GridWorks/sim-time-experiment/house0.imaginary.json"
OUT = Path("/Users/jessica/GridWorks/sim-time-experiment/sim_sensor_out")
TOPIC = "sim/sensor"  # sim/sensor/<ChannelName>

# the sensor quantities a SimSensor produces (relay/thermostat STATE is actuator
# output, heard by the plant, not emitted by the sensor side)
SENSOR_QUANTITIES = {"Temperature", "Power", "Voltage", "FlowRate"}

# plausible scripted value per TelemetryName (the plant would supply these)
def scripted_value(telemetry_name: str) -> int:
    return {
        "WaterTempCTimes1000": 48_500,    # 48.5 C tank water
        "AirTempFTimes1000": 70_000,      # 70.0 F room
        "PowerW": 1500,                   # 1.5 kW draw
        "MicroVolts": 1_000_000,          # 1.0 V thermistor divider
        "GpmTimes100": 250,               # 2.5 gpm
        "VoltsTimesTen": 240,             # 24.0 V
    }.get(telemetry_name, 0)


def sensor_channels(layout_path: str) -> list[dict]:
    d = json.load(open(layout_path))
    return [
        c for c in d.get("DataChannels", [])
        if c.get("Quantity") in SENSOR_QUANTITIES
    ]


class SimSensor:
    """Configured generically from the channels it captures; publishes a reading
    per channel. Stand-in for the SimSensorActor (one actor, any unit, any
    AboutNodeName)."""

    def __init__(self, channels: list[dict]) -> None:
        self.channels = channels
        self._c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._c.connect(HOST, PORT, keepalive=15)
        self._c.loop_start()

    def emit_round(self) -> None:
        now_ms = int(time.time() * 1000)
        for ch in self.channels:
            reading = {
                "ChannelName": ch["Name"],
                "AboutNodeName": ch.get("AboutNodeName"),
                "TelemetryName": ch.get("TelemetryName"),
                "Quantity": ch.get("Quantity"),
                "Value": scripted_value(ch.get("TelemetryName")),
                "ScadaReadTimeUnixMs": now_ms,
            }
            self._c.publish(f"{TOPIC}/{ch['Name']}", json.dumps(reading))

    def stop(self) -> None:
        self._c.loop_stop()
        self._c.disconnect()


class Observer:
    def __init__(self) -> None:
        self.seen: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._c.on_connect = lambda c, *_: c.subscribe(f"{TOPIC}/#")
        self._c.on_message = self._on_msg
        self._c.connect(HOST, PORT, keepalive=15)
        self._c.loop_start()

    def _on_msg(self, _c, _u, msg) -> None:
        try:
            r = json.loads(msg.payload)
        except Exception:
            return
        with self._lock:
            self.seen[r["ChannelName"]] = r

    def stop(self) -> None:
        self._c.loop_stop()
        self._c.disconnect()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    channels = sensor_channels(LAYOUT)
    expected = {c["Name"]: c.get("Quantity") for c in channels}

    observer = Observer()
    time.sleep(0.5)  # let the subscription land
    sensor = SimSensor(channels)
    for _ in range(3):
        sensor.emit_round()
        time.sleep(0.4)
    time.sleep(0.5)
    sensor.stop()
    observer.stop()

    seen = observer.seen
    # verify: exactly the expected channels, each with the right quantity, real value
    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))
    quantity_ok = all(seen[n]["Quantity"] == expected[n] for n in seen if n in expected)
    value_ok = all(isinstance(seen[n]["Value"], int) for n in seen)

    by_q: dict[str, int] = {}
    for n in seen:
        by_q[seen[n]["Quantity"]] = by_q.get(seen[n]["Quantity"], 0) + 1

    result = {
        "broker": f"{HOST}:{PORT}",
        "expected_channels": len(expected),
        "witnessed_channels": len(seen),
        "by_quantity_witnessed": by_q,
        "missing": missing,
        "extra": extra,
        "quantity_consistent": quantity_ok,
        "values_present": value_ok,
        "PASS": not missing and not extra and quantity_ok and value_ok,
        "sample": {n: seen[n] for n in list(seen)[:3]},
    }
    (OUT / "result.json").write_text(json.dumps(result, indent=2))
    json.dump([seen[n] for n in seen], open(OUT / "readings.jsonl", "w"))
    print(json.dumps({k: result[k] for k in
                      ("expected_channels", "witnessed_channels",
                       "by_quantity_witnessed", "missing", "extra",
                       "quantity_consistent", "PASS")}, indent=2))


if __name__ == "__main__":
    main()
