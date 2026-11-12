"""The temperatures, powers and flows of the running stack, from the reports
its scada persisted. Run by `plot_channels.py` inside the scada's
container:

    docker compose exec -T scada python - < channel_readings.py

A channel's kind is read off the unit the scada's layout gives it, and
each raw value is read in that unit. A tank depth is reported twice, as
the tank module's own temperature and as the temperature the scada derives
and acts on; only the second is kept. Every `channel.readings` is decoded
through the scada's vendored sema snapshot. Prints CSV, one row per
reading.
"""

import csv
import json
import sys
from pathlib import Path
from typing import NamedTuple

SCADA_REPO = Path.cwd()
sys.path.insert(0, str(SCADA_REPO / "gw_spaceheat"))
sys.path.insert(0, str(SCADA_REPO / "packages" / "gridworks-scada-protocol"))

from actors.sieg_loop import FLOW_UNITS, POWER_UNITS
from gwsproto.conversions.temperature import Temperature
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatChannelNames as HCN,
)
from sema_snapshot.sema.codec import SemaCodec
from sema_snapshot.sema.types import ChannelReadings
from sema_to_dc import load_layout

REPORT = "report.event"
CONFIG = Path.home() / ".config" / "gridworks" / "scada"
EVENTS = Path.home() / ".local" / "share" / "gridworks" / "scada" / "event"
TEMPERATURE = "temperature"
POWER = "power"
FLOW = "flow"


class Depth(NamedTuple):
    """Where a tank depth channel sits. Interior to the plot; the layout
    holds the same fact as the channel's name."""

    tank: str
    depth: int


class Reading(NamedTuple):
    """One reading in display units: degrees Celsius, watts or US gallons
    a minute by `kind`, with the tank and depth of a tank depth channel.
    Interior to the plot; the word it is read from is channel.readings."""

    unix_s: int
    channel: str
    kind: str
    value: float
    tank: str | None
    depth: int | None


def is_temperature(unit) -> bool:
    try:
        Temperature(0, unit)
    except ValueError:
        return False
    return True


def main() -> None:
    layout = load_layout(
        CONFIG / "hardware-layout.json", CONFIG / "operational-params.json"
    )
    registry = layout.channel_registry
    tanks = [HCN.buffer, *(layout.store_tanks[i] for i in sorted(layout.store_tanks))]
    depth_by_channel = {
        name: Depth(tank.reader, depth)
        for tank in tanks
        for depth, name in enumerate((tank.depth1, tank.depth2, tank.depth3), start=1)
    }
    module_temperatures = set().union(*(tank.devices for tank in tanks))
    codec = SemaCodec()
    kind_by_channel: dict[str, str | None] = {}

    def kind_of(channel: str) -> str | None:
        unit = registry.unit(channel)
        if channel in module_temperatures:
            return None
        if unit in POWER_UNITS:
            return POWER
        if unit in FLOW_UNITS:
            return FLOW
        if unit is not None and is_temperature(unit):
            return TEMPERATURE
        return None

    out = csv.writer(sys.stdout)
    out.writerow(Reading._fields)
    for path in sorted(EVENTS.glob("*/*.json")):
        event = json.loads(path.read_text())
        if event["TypeName"] != REPORT:
            continue
        for one in event["Report"]["ChannelReadingList"]:
            readings = codec.from_dict(one, auto_upgrade=False, expect=ChannelReadings)
            channel = readings.channel_name
            if channel not in kind_by_channel:
                kind_by_channel[channel] = kind_of(channel)
            kind = kind_by_channel[channel]
            if kind is None:
                continue
            where = depth_by_channel.get(channel)
            for raw, unix_ms in zip(
                readings.value_list, readings.scada_read_time_unix_ms_list, strict=True
            ):
                if kind == TEMPERATURE:
                    value = round(registry.temperature(channel, raw).c, 2)
                elif kind == FLOW:
                    value = raw / 100
                else:
                    value = raw
                out.writerow(
                    Reading(
                        unix_ms // 1000,
                        channel,
                        kind,
                        value,
                        where.tank if where else None,
                        where.depth if where else None,
                    )
                )


if __name__ == "__main__":
    main()
