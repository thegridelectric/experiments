"""What the scada of the running stack has reported, from the events it
persisted. Run by `check.py` inside the scada's container:

    docker compose exec -T scada python - < stack_check.py

Every `channel.readings` of a `report.event` is decoded through the
scada's vendored sema snapshot, and so is the whole event, to count the
ones the snapshot refuses; a `gridworks.event.shutdown` is gwproactor's own
event, read as that. Prints one JSON object.
"""

import json
import sys
from pathlib import Path
from typing import NamedTuple

SCADA_REPO = Path.cwd()
sys.path.insert(0, str(SCADA_REPO / "gw_spaceheat"))
sys.path.insert(0, str(SCADA_REPO / "packages" / "gridworks-scada-protocol"))

from gwproto.messages import ShutdownEvent  # noqa: E402
from gwsproto.data_classes.components import (  # noqa: E402
    ElectricMeterComponent,
    SimPicoBtuMeterComponent,
    SimPicoTankModuleComponent,
    SimSensorComponent,
)
from gwsproto.data_classes.sh_node import ShNode  # noqa: E402
from gwsproto.enums import ActorClass, SimDeviceType  # noqa: E402
from sema_snapshot.sema.base import SemaError  # noqa: E402
from sema_snapshot.sema.codec import SemaCodec  # noqa: E402
from sema_snapshot.sema.types import ChannelReadings, ReportEvent  # noqa: E402

from sema_to_dc import load_layout  # noqa: E402

REPORT = "report.event"
SHUTDOWN = "gridworks.event.shutdown"
CONFIG = Path.home() / ".config" / "gridworks" / "scada"
EVENTS = Path.home() / ".local" / "share" / "gridworks" / "scada" / "event"


class ChannelSeen(NamedTuple):
    """What the reports hold for one channel. Interior to this check; no
    word carries a per-channel run summary."""

    readings: int
    distinct_values: int
    low: int
    high: int
    last: int


def senses_the_plant(node: ShNode) -> bool:
    """Whether what this node's device senses comes from the plant link."""
    component = node.component
    if isinstance(
        component,
        (SimSensorComponent, SimPicoTankModuleComponent, SimPicoBtuMeterComponent),
    ):
        return True
    if isinstance(component, ElectricMeterComponent):
        return component.device_type.DeviceType == SimDeviceType.SimPowerMeter
    return False


def main() -> None:
    layout = load_layout(
        CONFIG / "hardware-layout.json", CONFIG / "operational-params.json"
    )
    plant_fed = set(
        layout.enabled_channel_names(
            channel.Name
            for channel in layout.data_channels.values()
            if senses_the_plant(layout.nodes[channel.CapturedByNodeName])
        )
    )
    codec = SemaCodec()
    reports = 0
    refused: list[str] = []
    shutdowns: list[ShutdownEvent] = []
    values: dict[str, list[int]] = {}
    for path in sorted(EVENTS.glob("*/*.json")):
        event = json.loads(path.read_text())
        if event["TypeName"] == REPORT:
            reports += 1
            for one in event["Report"]["ChannelReadingList"]:
                readings = codec.from_dict(
                    one, auto_upgrade=False, expect=ChannelReadings
                )
                values.setdefault(readings.channel_name, []).extend(readings.value_list)
            try:
                codec.from_dict(event, auto_upgrade=False, expect=ReportEvent)
            except (SemaError, ValueError) as e:
                refused.append(str(e))
        elif event["TypeName"] == SHUTDOWN:
            shutdowns.append(ShutdownEvent.model_validate(event))

    seen = {
        name: ChannelSeen(len(vs), len(set(vs)), min(vs), max(vs), vs[-1])
        for name, vs in values.items()
    }
    print(
        json.dumps(
            {
                "reports": reports,
                "reports_the_snapshot_refuses": len(refused),
                "first_refusal": refused[0] if refused else None,
                "shutdown_reasons": [s.Reason for s in shutdowns],
                "plant_fed_channels": sorted(plant_fed),
                "relays": sorted(
                    node.name
                    for node in layout.nodes.values()
                    if node.actor_class == ActorClass.Relay
                ),
                "seen": {name: seen[name]._asdict() for name in sorted(seen)},
            }
        )
    )


if __name__ == "__main__":
    main()
