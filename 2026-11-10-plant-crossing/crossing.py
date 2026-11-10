"""The scada's side of the plant crossing, with a witness.

Run from gridworks-scada, with `ta-plant` already up on the dev broker:

    uv run --locked python ../experiments/2026-11-10-plant-crossing/crossing.py

Three parties on the dev broker's MQTT face (localhost:1885):

- the scada's `BrokerPlantLink`, built from the no-sieg House0 fixture's
  aliases, with one sensor claiming every channel the scada's own layout
  says a simulated sensing device captures;
- a witness: a paho client of its own that subscribes to every `gw` topic
  carrying a sim.plant word and decodes each payload through the scada's
  vendored sema snapshot;
- the plant, a separate process on the AMQP face.

Prints one JSON verdict and exits 0 on PASS.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

SCADA_REPO = Path.cwd()
sys.path.insert(0, str(SCADA_REPO / "gw_spaceheat"))
sys.path.insert(0, str(SCADA_REPO / "packages" / "gridworks-scada-protocol"))

from gwproactor.config import MQTTClient  # noqa: E402
from gwproactor.config.mqtt import TLSInfo  # noqa: E402
from gwsproto.enums import ChangeRelayPin, SimDeviceType  # noqa: E402
from sema_snapshot.sema.codec import SemaCodec  # noqa: E402
from sema_snapshot.sema.types import SimPlantActuation, SimPlantFlux  # noqa: E402

from clock import WallClock  # noqa: E402
from plant_link import PLANT_SILENT_AFTER_S, BrokerPlantLink, PlantReadings  # noqa: E402
from sema_to_dc import load_layout  # noqa: E402

CONFIG = SCADA_REPO / "tests" / "config"
PAIR = "gw.house0.no.sieg.hazel"
MQTT_HOST = "localhost"
MQTT_PORT = 1885
FLUXES_WANTED = 4
RELAY = "store-pump-relay"
TIMEOUT_S = 60.0


def simulated_sensing_channels(layout) -> set[str]:
    """The scada's own answer to which channels the plant feeds: those
    captured by a node whose component is a simulated device."""
    simulated = set(SimDeviceType.values())
    names = set()
    for channel in layout.data_channels.values():
        node = layout.nodes[channel.CapturedByNodeName]
        component = node.component
        if component is None:
            continue
        if getattr(component.gt, "DeviceType", None) in simulated:
            names.add(channel.Name)
    return names


class Witness:
    def __init__(self) -> None:
        self.codec = SemaCodec()
        self.fluxes: list[SimPlantFlux] = []
        self.actuations: list[SimPlantActuation] = []
        self.undecodable: list[str] = []
        self.topics: set[str] = set()
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = lambda client, *_: client.subscribe("gw/#")
        self.client.on_message = self.on_message

    def on_message(self, _client, _userdata, msg) -> None:
        if "sim-plant" not in msg.topic:
            return
        self.topics.add(msg.topic)
        try:
            word = self.codec.from_dict(json.loads(msg.payload)["Payload"], auto_upgrade=False)
        except Exception as e:  # noqa: BLE001
            self.undecodable.append(f"{msg.topic}: {e}")
            return
        if isinstance(word, SimPlantFlux):
            self.fluxes.append(word)
        elif isinstance(word, SimPlantActuation):
            self.actuations.append(word)
        else:
            self.undecodable.append(f"{msg.topic}: {type(word).__name__}")

    def start(self) -> None:
        self.client.connect(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


async def run() -> dict:
    layout = load_layout(
        CONFIG / f"{PAIR}.layout.json", CONFIG / f"{PAIR}.operational.params.json"
    )
    expected = simulated_sensing_channels(layout)
    link = BrokerPlantLink(
        config=MQTTClient(host=MQTT_HOST, port=MQTT_PORT, tls=TLSInfo(use_tls=False)),
        scada_alias=layout.scada_g_node_alias,
        plant_alias=layout.terminal_asset_g_node_alias,
        clock=WallClock(),
        silent_after_s=PLANT_SILENT_AFTER_S,
        monotonic=time.monotonic,
    )
    delivered: list[PlantReadings] = []
    link.sense(sorted(expected), delivered.append)

    witness = Witness()
    witness.start()

    # Held before the link has a connection: nothing has been told the
    # plant, so the plant can learn this position only by being restated.
    link.set_relay(RELAY, ChangeRelayPin.Energize)
    link.start()

    deadline = time.monotonic() + TIMEOUT_S
    while len(delivered) < FLUXES_WANTED and time.monotonic() < deadline:
        await asyncio.sleep(0.2)

    link.set_relay(RELAY, ChangeRelayPin.DeEnergize)
    await asyncio.sleep(2.0)
    link.stop()
    witness.stop()

    link_channels = {name for readings in delivered for name in readings.channel_names}
    witness_channels = [set(f.channel_name_list) for f in witness.fluxes]
    moved = sorted(
        name
        for name in expected
        if len({r.values[r.channel_names.index(name)] for r in delivered if name in r.channel_names}) > 1
    )
    checks = {
        "link heard the wanted fluxes": len(delivered) >= FLUXES_WANTED,
        "link: every sensed channel, none extra": link_channels == expected
        and link.unsensed_channels == set(),
        "witness decoded every flux through the snapshot": len(witness.fluxes) >= FLUXES_WANTED
        and witness.undecodable == [],
        "witness: every sensed channel, none extra, in every flux": bool(witness_channels)
        and all(channels == expected for channels in witness_channels),
        "values drift": len(moved) == len(expected),
        "witness saw the restated Energize and the DeEnergize": [
            a.action.value for a in witness.actuations if a.relay_name == RELAY
        ][-1:]
        == ["DeEnergize"]
        and any(a.action.value == "Energize" for a in witness.actuations),
    }
    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "expected_channels": len(expected),
        "fluxes_to_link": len(delivered),
        "fluxes_to_witness": len(witness.fluxes),
        "channels_that_moved": len(moved),
        "unsensed_channels": sorted(link.unsensed_channels),
        "extra_or_missing_at_link": sorted(link_channels ^ expected),
        "actuations_on_the_wire": [
            [a.relay_name, a.action.value] for a in witness.actuations
        ],
        "undecodable": witness.undecodable,
        "topics": sorted(witness.topics),
    }


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["verdict"] == "PASS" else 1)
