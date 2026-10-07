"""What this folder knows about each house beyond its channel words:
which distribution systems the hourly files hold, and which zone pair
the minute-level analyses compare.

Maple is two distribution systems: a panel heater was added in the
first week of January 2026, so its hours before and after are `maple1`
and `maple2`. The hourly data dates the change: the emitters' output
per degree of water temperature above the room steps up between
MAPLE1_END and MAPLE2_START, and the days between belong to neither.
Every other house is one system for the whole season.
"""

import datetime
from pathlib import Path
from typing import NamedTuple

from pydantic import TypeAdapter

from gwexp.sema.property_format import LeftRightDot, SpaceheatName
from pull_readings import ET
from records import HourlyFile, HourRecord, MinuteFile

HERE = Path(__file__).parent
MAPLE1_END = datetime.date(2026, 1, 2)  # last day of maple1
MAPLE2_START = datetime.date(2026, 1, 9)  # first day of maple2


def ta_alias(house: str) -> LeftRightDot:
    """The terminal asset alias of a Millinocket house by its short name."""
    return TypeAdapter(LeftRightDot).validate_python(
        f"hw1.isone.me.versant.keene.{house}.ta"
    )


class System(NamedTuple):
    """One distribution system and its valid hours, in time order."""

    name: str  # the house, or `maple1` / `maple2`
    hours: list[HourRecord]


class ZonePair(NamedTuple):
    """The two zones a minute-level analysis compares: one that calls
    for long stretches and one that calls seldom and shares the loop.
    Each is the zone's thermostat white-wire power channel."""

    steady: SpaceheatName
    idle: SpaceheatName


# Houses whose minute file has been pulled, with the zone pair their
# analyses use. Validated at import so a misspelled channel fails here.
ZONE_PAIRS: dict[str, ZonePair] = {
    "beech": ZonePair(steady="zone1-down-whitewire-pwr", idle="zone2-up-whitewire-pwr"),
}
TypeAdapter(dict[str, ZonePair]).validate_python(ZONE_PAIRS)


def hour_day(hour: HourRecord) -> datetime.date:
    """The Eastern calendar day an hourly record starts in."""
    return datetime.datetime.fromtimestamp(hour.hour_start_s, ET).date()


def hourly_files() -> list[HourlyFile]:
    """Every hourly file in this folder, by house name."""
    return [HourlyFile.read(p) for p in sorted(HERE.glob("*-hourly.dist.json"))]


def minute_file(house: str) -> MinuteFile:
    """The one minute file this folder holds for a house."""
    return MinuteFile.read(next(HERE.glob(f"*.{house}.ta-*-minute.pump.json")))


def systems() -> list[System]:
    """One System per distribution system, in name order."""
    out: list[System] = []
    for f in hourly_files():
        if f.house != "maple":
            out.append(System(f.house, f.hours))
            continue
        out.append(System("maple1", [h for h in f.hours if hour_day(h) <= MAPLE1_END]))
        out.append(System("maple2", [h for h in f.hours if hour_day(h) >= MAPLE2_START]))
    return out
