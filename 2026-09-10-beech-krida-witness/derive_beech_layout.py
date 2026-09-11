#!/usr/bin/env python3
"""Derive beech's WINDOW layout pair from the scada House0 fixture pair.

The scada test fixture (`gridworks-scada/tests/config/gw.house0.layout.json`
+ `.operational.params.json`) is the one House0 layout in the per-relay
shape (rung 3 of the relay decommission): a `scada.board.component.gt`
for the Krida panel and one `i2c.relay.component.gt` per relay. It
describes the fictional one-zone orange1 house. Beech is a two-zone
House0 (down, up) on the same Krida panel at 0x20/0x21, so its window
layout is the fixture with three edits, applied here by script so the
derivation is reproducible rather than a hand-edited file:

1. identity: orange1's three GNodes become beech's real hw1 aliases and
   GNodeIds (read off the deployed layout on the box, 2026-09-10);
2. zone 1 is renamed main -> down;
3. zone 2 (up) is cloned from zone 1: relays 19/20 (Krida markings) with
   their thin components, nodes, state channels, the thermostat poller,
   the whitewire power channel, the call circuit, and the capture
   tunings. Zone-private ids are remapped deterministically (uuid5 of
   the old id), shared ids (the board, the hubitat, the meter) are not;
4. beech's instruments for the heat call: the fixture's simulated meter
   becomes beech's real eGauge (EgaugePowerMeter, eGauge6069.local,
   the deployed layout's register map, plus `dist-pump-pwr` at 9010 and
   its `dist-pump` node), and beech's `dist-btu` pico BTU meter is added
   (pico_47352a: `dist-flow`, `dist-swt`, `dist-rwt`), so the window's
   snapshots carry distribution flow and pump power; the web server
   listens on 8000, where beech's picos post.

The ops params take ActuationAuthority=Standby so the window's local
control never actuates on its own; admin drives the relays.

Everything else in the fixture stays as it is (simulated tank modules, a
hubitat that is not beech's, a simulated meter): the window exists to
witness the relay path on the real panel, nothing else in the layout is
claimed to be beech.

    python3 derive_beech_layout.py [fixture_dir] [out_dir]
"""

import copy
import json
import sys
import uuid
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "gridworks-scada" / "tests" / "config"
OUT_DIR = Path(__file__).resolve().parent / "instances"
LAYOUT_FILE = "beech-window-gw.house0.layout-000.json"
OPS_FILE = "beech-window-gw.house0.operational.params-000.json"

ORANGE = "d1.isone.ct.newhaven.orange1"
BEECH = "hw1.isone.me.versant.keene.beech"
# Deployed beech layout, 2026-09-10 (GNodeClass -> GNodeId).
BEECH_GNODE_IDS = {
    "LeafTransactiveNode": "4da8659f-d455-45f2-ac63-16817c1a6322",
    "TerminalAsset": "7e152072-c91b-49d2-9ebd-f4fe1b684d06",
    "Scada": "19ee09df-80ba-437b-b6c1-1eebe9d34801",
}
ORANGE_DISPLAY = "Little Orange House Garage Heating System"
BEECH_DISPLAY = "Beech"

ZONE1_OLD, ZONE1_NEW = "zone1-main", "zone1-down"
ZONE2 = "zone2-up"
ZONE_CLONE_SUBS = [
    (ZONE1_NEW, ZONE2),
    ("Down Zone 1", "Up Zone 2"),
    ("Zone 1", "Zone 2"),
    ("Thermostat 1 for down", "Thermostat 2 for up"),
    ("Relay17", "Relay19"),
    ("Relay18", "Relay20"),
]
ZONE_CLONE_NS = uuid.UUID("6f1c2a4e-3b7d-4d1e-9c8a-2e5b7f9d0a11")

# 4. beech instruments (deployed beech layout, 2026-09-10)
EGAUGE = {"ModbusHost": "eGauge6069.local", "ModbusPort": 502, "HwUid": "BP01349"}
# channel -> (eGauge register, about node, AsyncCaptureDelta W); the fixture's
# meter channels that beech meters keep their entries, dist-pump-pwr is added.
EGAUGE_REGISTERS = {
    "hp-odu-pwr": (9006, "hp-odu", 300),
    "store-pump-pwr": (9014, "store-pump", 1),
    "zone1-down-whitewire-pwr": (9018, "zone1-down-whitewire", 1),
    "zone2-up-whitewire-pwr": (9020, "zone2-up-whitewire", 1),
    "dist-pump-pwr": (9010, "dist-pump", 1),
}
DIST_BTU = {
    "TypeName": "pico.btu.meter.component.gt", "Version": "000",
    "ComponentId": "f9578a29-73f0-474f-913c-fded698eac09",
    "DeviceType": "Gw101", "DisplayName": "dist-btu BtuMeter", "HwUid": "pico_47352a",
    "Enabled": True, "SerialNumber": "NA",
    "FlowChannelName": "dist-flow", "HotChannelName": "dist-swt", "ColdChannelName": "dist-rwt",
    "ReadCtVoltage": False, "SendHz": False,
    "FlowMeterType": "SAIER__SENHZG1WA", "HzCalcMethod": "UniformWindow",
    "TempCalcMethod": "SimpleBeta", "GpmFromHzMethod": "Constant",
    "ThermistorBeta": 3977, "GallonsPerPulse": 0.0009,
    "AsyncCaptureDeltaGpmX100": 10, "AsyncCaptureDeltaCelsiusX100": 20,
}
# deployed beech ShNodeIds / channel ids, so the window's readings carry beech's own ids
BEECH_IDS = {
    "dist-btu": "aa081b9e-0d14-498c-a575-79a6d4f8a0b0",
    "dist-flow": "c04ef85d-7384-44d5-a056-8c2eaa2c49d3",
    "dist-swt": "165e39d9-e8c4-4e68-b7c5-d8435abea05c",
    "dist-rwt": "6ad91e8e-e1ee-46b4-b06b-e47c64074dc4",
    "dist-pump": "0f0c5cb7-2343-42d0-9d7f-accca67076b0",
}
BEECH_CHANNEL_IDS = {
    "dist-flow": "2006b63a-a99d-4384-82c6-48f374d967f1",
    "dist-swt": "5dae9382-a2b1-4f11-9259-3f3f026944ab",
    "dist-rwt": "2fe25fbf-400a-418e-b2dc-35e3b62f8250",
    "dist-pump-pwr": "a2ebe9fa-05ba-4665-a6ba-dbc85aee530c",
}


def text_sub(obj, subs):
    s = json.dumps(obj)
    for old, new in subs:
        s = s.replace(old, new)
    return json.loads(s)


def uuids_in(obj) -> set[str]:
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            try:
                uuid.UUID(x)
                found.add(x)
            except ValueError:
                pass

    walk(obj)
    return found


def mentions(obj, needle: str) -> bool:
    return needle in json.dumps(obj)


def derive(layout: dict, ops: dict) -> tuple[dict, dict]:
    # 1. identity
    layout = text_sub(layout, [(ORANGE, BEECH), (ORANGE_DISPLAY, BEECH_DISPLAY)])
    ops = text_sub(ops, [(ORANGE, BEECH)])
    for g in layout["GNodes"]:
        g["GNodeId"] = BEECH_GNODE_IDS[g["GNodeClass"]]

    # 2. zone 1 main -> down
    layout = text_sub(layout, [(ZONE1_OLD, ZONE1_NEW), ("Main Zone", "Down Zone"), ("for main", "for down")])
    ops = text_sub(ops, [(ZONE1_OLD, ZONE1_NEW)])
    for circuit in layout["Hydronic"]["ZoneCallCircuits"]:
        if circuit["ServesZone"] == "main":
            circuit["ServesZone"] = "down"
    for zone in layout["Hydronic"]["Zones"]:
        if zone["Name"] == "main":
            zone["Name"] = "down"

    # 3. zone 2 up, cloned from zone 1
    zone_objects: list = []
    zone_lists: list[tuple[list, list]] = []  # (target list, elements to clone)
    for key in ("Components", "DataChannels", "DerivedChannels", "ShNodes"):
        picked = []
        for element in layout[key]:
            if element.get("TypeName") == "electric.meter.component.gt":
                inner = [e for e in element["ConfigList"] if mentions(e, ZONE1_NEW)]
                zone_lists.append((element["ConfigList"], inner))
                zone_objects += inner
            elif mentions(element, ZONE1_NEW):
                picked.append(element)
        zone_lists.append((layout[key], picked))
        zone_objects += picked
    for key in ("ZoneCallCircuits", "Zones"):
        picked = [c for c in layout["Hydronic"][key] if mentions(c, ZONE1_NEW)]
        zone_lists.append((layout["Hydronic"][key], picked))
        zone_objects += picked
    tunings = [t for t in ops["CaptureTuningList"] if mentions(t, ZONE1_NEW)]
    zone_lists.append((ops["CaptureTuningList"], tunings))

    # ids private to zone 1: every occurrence in the layout is inside a zone-1 object
    zone_ids = set().union(*(uuids_in(o) for o in zone_objects))
    everything_else = copy.deepcopy(layout)
    for key in ("Components", "DataChannels", "DerivedChannels", "ShNodes"):
        everything_else[key] = [e for e in layout[key] if not mentions(e, ZONE1_NEW)]
    everything_else["Hydronic"]["ZoneCallCircuits"] = []
    everything_else["Hydronic"]["Zones"] = []
    shared_ids = uuids_in(everything_else)
    private_ids = zone_ids - shared_ids
    # deterministic but v4-shaped (the gwsproto id format requires version 4)
    id_subs = [
        (old, str(uuid.UUID(bytes=uuid.uuid5(ZONE_CLONE_NS, old).bytes, version=4)))
        for old in sorted(private_ids)
    ]

    for target, elements in zone_lists:
        for element in elements:
            clone = text_sub(element, ZONE_CLONE_SUBS + id_subs)
            if clone.get("TypeName") == "gw1.zone.call.circuit":
                clone["ServesZone"] = "up"
                clone["CircuitPosition"] = 2
            if clone.get("TypeName") == "gw1.hvac.zone":
                clone["Name"] = "up"
                clone["Critical"] = True  # beech: both zones critical
            target.append(clone)

    # 4. beech instruments
    ta = f"{BEECH}.ta"
    meter = next(c for c in layout["Components"] if c["TypeName"] == "electric.meter.component.gt")
    meter["DeviceType"] = "EgaugePowerMeter"
    meter["DisplayName"] = "EGauge Power Meter"
    meter.update(EGAUGE)
    kept = [e for e in meter["ConfigList"] if e["ChannelName"] in EGAUGE_REGISTERS]
    dropped = [e["ChannelName"] for e in meter["ConfigList"] if e["ChannelName"] not in EGAUGE_REGISTERS]
    if dropped:
        raise SystemExit(f"fixture meter channels beech does not meter: {dropped}")
    if "dist-pump-pwr" not in [e["ChannelName"] for e in kept]:
        kept.append({"ChannelName": "dist-pump-pwr", "TypeName": "electric.meter.channel.config", "Version": "000"})
    for e in kept:
        address, about, _ = EGAUGE_REGISTERS[e["ChannelName"]]
        e["EgaugeRegisterConfig"] = {
            "Address": address, "Name": about, "Denominator": 1, "Description": "change in value",
            "Type": "f32", "Unit": "W", "TypeName": "egauge.register.config", "Version": "000",
        }
        e.pop("Exponent", None)
        e.pop("Unit", None)
    meter["ConfigList"] = kept
    meter_dt = next(t for t in layout["DeviceTypes"] if t["TypeName"] == "electric.meter.device.type.gt")
    meter_dt["DeviceType"] = "EgaugePowerMeter"
    meter_dt["DisplayName"] = "EGauge 4030"

    def node(name, display, actor="NoActor", **kw):
        return {"TypeName": "spaceheat.node.gt", "Version": "303", "ShNodeId": BEECH_IDS[name],
                "Name": name, "DisplayName": display, "ActorClass": actor, **kw}

    def channel(name, display, about, captured_by, telemetry, quantity, **kw):
        return {"TypeName": "data.channel.gt", "Version": "003", "Id": BEECH_CHANNEL_IDS[name],
                "Name": name, "DisplayName": display, "AboutNodeName": about,
                "CapturedByNodeName": captured_by, "TelemetryName": telemetry, "Quantity": quantity,
                "TerminalAssetAlias": ta, **kw}

    def tuning(name, poll_ms, delta):
        return {"TypeName": "capture.tuning", "Version": "000", "ChannelName": name, "PollPeriodMs": poll_ms,
                "CapturePeriodS": 300, "AsyncCapture": True, "AsyncCaptureDelta": delta}

    names = {n["Name"] for n in layout["ShNodes"]}
    layout["ShNodes"] += [n for n in (
        node("dist-pump", "Dist Pump"),
        node("dist-btu", "Dist Btu", "ApiBtuMeter", ActorHierarchyName="s.dist-btu", ComponentId=DIST_BTU["ComponentId"]),
        node("dist-swt", "Dist Swt"),
        node("dist-rwt", "Dist Rwt"),
    ) if n["Name"] not in names]
    layout["Components"].append(DIST_BTU)
    layout["DataChannels"] = [c for c in layout["DataChannels"] if c["Name"] not in BEECH_CHANNEL_IDS] + [
        channel("dist-pump-pwr", "DIST PUMP PWR", "dist-pump", "power-meter", "PowerW", "Power", InPowerMetering=False),
        channel("dist-flow", "Dist Flow Gpm X 100", "dist-flow", "dist-btu", "GpmTimes100", "FlowRate"),
        channel("dist-swt", "Dist Swt Celsius X 1000", "dist-swt", "dist-btu", "WaterTempCTimes1000", "Temperature"),
        channel("dist-rwt", "Dist Rwt Celsius X 1000", "dist-rwt", "dist-btu", "WaterTempCTimes1000", "Temperature"),
    ]
    ops["CaptureTuningList"] = [t for t in ops["CaptureTuningList"] if t["ChannelName"] not in BEECH_CHANNEL_IDS] + [
        tuning("dist-pump-pwr", 1000, 1),
        tuning("dist-flow", 1000, 10),
        tuning("dist-swt", 1000, 20),
        tuning("dist-rwt", 1000, 20),
    ]

    # beech's picos post to port 8000 (the deployed scada listens there)
    web = next(c for c in layout["Components"] if c["TypeName"] == "web.server.component.gt")
    web["WebServer"]["Port"] = 8000

    # window posture
    ops["ActuationAuthority"] = "Standby"
    return layout, ops, id_subs


def main(argv: list[str]) -> int:
    fixture_dir = Path(argv[0]) if argv else FIXTURE_DIR
    out_dir = Path(argv[1]) if len(argv) > 1 else OUT_DIR
    layout = json.loads((fixture_dir / "gw.house0.layout.json").read_text())
    ops = json.loads((fixture_dir / "gw.house0.operational.params.json").read_text())
    layout, ops, id_subs = derive(layout, ops)
    out_dir.mkdir(parents=True, exist_ok=True)
    # experiments instance grammar: <subject>-<condition>-<type.name>-<version>.json
    (out_dir / LAYOUT_FILE).write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n")
    (out_dir / OPS_FILE).write_text(json.dumps(ops, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out_dir}/{LAYOUT_FILE} + {OPS_FILE}; {len(id_subs)} zone-private ids remapped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
