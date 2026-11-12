"""The verdict on one loop run, from what the scada left on disk.

Run by `run.sh` from gridworks-scada after the scada and the plant stop:

    uv run --locked python ../experiments/2026-11-10-plant-loop/loop_check.py <scratch> <logs>

Reads the scada's persisted events under the scratch XDG data home. Every
`report.event` is decoded through the scada's vendored sema snapshot; a
`gridworks.event.shutdown` is gwproactor's own event, read as that.

Prints one JSON verdict and exits 0 on PASS.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

SCADA_REPO = Path.cwd()
sys.path.insert(0, str(SCADA_REPO / "gw_spaceheat"))
sys.path.insert(0, str(SCADA_REPO / "packages" / "gridworks-scada-protocol"))

from gwproto.messages import ShutdownEvent  # noqa: E402
from gwsproto.data_classes.components import (  # noqa: E402
    ElectricMeterComponent,
    GpioSensorComponent,
    I2cThermistorReaderComponent,
    SimPicoBtuMeterComponent,
    SimPicoTankModuleComponent,
    SimSensorComponent,
)
from gwsproto.data_classes.sh_node import ShNode  # noqa: E402
from gwsproto.enums import SimDeviceType  # noqa: E402
from sema_snapshot.sema.codec import SemaCodec  # noqa: E402
from sema_snapshot.sema.types import ReportEvent  # noqa: E402

from sema_to_dc import load_layout  # noqa: E402

REPORT = "report.event"
SHUTDOWN = "gridworks.event.shutdown"
ALIVE_MARK = "scada alive at the end of the window"
STARTING_MARK = "scada starting"


class ChannelSeen(NamedTuple):
    """What the reports hold for one channel across the run. Interior to
    this check; no word carries a per-channel run summary."""

    readings: int
    distinct_values: int
    low: int
    high: int


def mark_ms(clock: Path, mark: str) -> int | None:
    for line in clock.read_text().splitlines():
        stamp, _, text = line.partition(" ")
        if text == mark:
            return int(datetime.fromisoformat(stamp).timestamp() * 1000)
    return None


def senses_the_plant(node: ShNode) -> bool:
    """Whether what this node's device senses comes from the plant link:
    a sim sensor or sim pico word, a simulated power meter, or a sensing
    device on a simulated board."""
    component = node.component
    if isinstance(
        component, (SimSensorComponent, SimPicoTankModuleComponent, SimPicoBtuMeterComponent)
    ):
        return True
    if isinstance(component, ElectricMeterComponent):
        return component.device_type.DeviceType == SimDeviceType.SimPowerMeter
    if isinstance(component, (GpioSensorComponent, I2cThermistorReaderComponent)):
        return component.board_component.simulated
    return False


def plant_fed_channels(scratch: Path) -> set[str]:
    """The channels the scada takes from the plant link, by the scada's
    own layout loader."""
    config = scratch / "config" / "gridworks" / "scada"
    layout = load_layout(config / "hardware-layout.json", config / "operational-params.json")
    return set(
        layout.enabled_channel_names(
            channel.Name
            for channel in layout.data_channels.values()
            if senses_the_plant(layout.nodes[channel.CapturedByNodeName])
        )
    )


def main() -> int:
    scratch, logs = Path(sys.argv[1]), Path(sys.argv[2])
    clock = logs / "clock.txt"
    started_ms = mark_ms(clock, STARTING_MARK)
    alive_ms = mark_ms(clock, ALIVE_MARK)
    codec = SemaCodec()

    reports: list[ReportEvent] = []
    shutdowns: list[ShutdownEvent] = []
    for path in sorted((scratch / "data" / "gridworks" / "scada" / "event").glob("*/*.json")):
        event = json.loads(path.read_text())
        if event["TypeName"] == REPORT:
            reports.append(codec.from_dict(event, auto_upgrade=False, expect=ReportEvent))
        elif event["TypeName"] == SHUTDOWN:
            shutdowns.append(ShutdownEvent.model_validate(event))

    values: dict[str, list[int]] = {}
    for event in reports:
        for readings in event.report.channel_reading_list:
            values.setdefault(readings.channel_name, []).extend(readings.value_list)
    seen = {
        name: ChannelSeen(len(vs), len(set(vs)), min(vs), max(vs))
        for name, vs in values.items()
    }

    expected = plant_fed_channels(scratch)
    unchanged = sorted(
        name for name in expected if name not in seen or seen[name].distinct_values < 2
    )
    window_s = (alive_ms - started_ms) / 1000 if started_ms and alive_ms else 0
    # A stop the run did not ask for: any shutdown before the window closed,
    # or one that was not the run's own SIGINT.
    early_or_unasked = [
        s.Reason
        for s in shutdowns
        if alive_ms is None or s.TimeCreatedMs < alive_ms or "SIGINT" not in s.Reason
    ]
    checks = {
        "scada alive at the end of the window": alive_ms is not None,
        "no shutdown but the run's own stop": early_or_unasked == [] and len(shutdowns) == 1,
        "a report for most minutes of the window": window_s >= 60
        and len(reports) >= int(window_s // 60) - 1,
        "every plant-fed channel is in the reports": expected <= set(seen),
        "every plant-fed channel changed": bool(expected) and unchanged == [],
    }
    result = {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "window_s": window_s,
        "reports": len(reports),
        "plant_fed_channels": len(expected),
        "unchanged_or_missing": unchanged,
        "shutdown_reasons": [s.Reason for s in shutdowns],
        "seen": {name: seen[name]._asdict() for name in sorted(expected & set(seen))},
    }
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
