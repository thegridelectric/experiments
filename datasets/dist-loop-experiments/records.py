"""The two kind-specific data files this folder commits, as typed
records: an hourly reduction of a house's distribution loop and a
minute reduction with the pump and the zone calls.

No sema word holds an hourly or minute aggregate of a channel yet; a
word for aggregated channel readings retires both files and this
module. Until then the dict form of each record appears here only, at
the serialization boundary (`to_jsonable` / `from_jsonable`), and
every reader gets attributes, not keys.
"""

import datetime
import json
from pathlib import Path
from typing import NamedTuple

import numpy as np

from gwexp.sema.property_format import LeftRightDot, SpaceheatName, UTCSeconds
from pull_readings import ET
from tables import Table


class HourRecord(NamedTuple):
    """One hour of a house's distribution loop, reduced from the 10 s
    grid over the hour's valid samples."""

    hour_start_s: UTCSeconds  # the hour's first second
    valid_fraction: float  # share of the hour with fresh temperature readings
    flowing_fraction: float  # share of valid samples with the loop circulating
    mean_gpm: float  # mean flow over valid samples, zero-flow samples included
    source_f: float | None  # flow-weighted source temperature; None with no flow
    return_f: float | None  # flow-weighted return temperature; None with no flow
    heat_kwh: float  # heat delivered to distribution in the hour

    def to_jsonable(self) -> dict[str, float | int | None]:
        return {
            "HourStartS": self.hour_start_s,
            "ValidFraction": round(self.valid_fraction, 4),
            "FlowingFraction": round(self.flowing_fraction, 4),
            "MeanGpm": round(self.mean_gpm, 3),
            "SourceF": None if self.source_f is None else round(self.source_f, 2),
            "ReturnF": None if self.return_f is None else round(self.return_f, 2),
            "HeatKwh": round(self.heat_kwh, 3),
        }

    @classmethod
    def from_jsonable(cls, d: dict) -> "HourRecord":
        return cls(
            hour_start_s=int(d["HourStartS"]),
            valid_fraction=float(d["ValidFraction"]),
            flowing_fraction=float(d["FlowingFraction"]),
            mean_gpm=float(d["MeanGpm"]),
            source_f=None if d["SourceF"] is None else float(d["SourceF"]),
            return_f=None if d["ReturnF"] is None else float(d["ReturnF"]),
            heat_kwh=float(d["HeatKwh"]),
        )

    @property
    def drop_f(self) -> float:
        """Source minus return; only for an hour with flow."""
        assert self.source_f is not None and self.return_f is not None
        return self.source_f - self.return_f


class HourlyFile(NamedTuple):
    """`<ta>-<start>.<end>-hourly.dist.json`: one house's season of
    HourRecords, one per hour that had enough valid samples. The window
    is Eastern calendar days, end exclusive."""

    ta_alias: LeftRightDot
    start_day_et: datetime.date
    end_day_et: datetime.date
    hours: list[HourRecord]

    @property
    def house(self) -> str:
        """The house segment of the alias (`beech`)."""
        return self.ta_alias.split(".")[-2]

    def to_jsonable(self) -> dict:
        return {
            "TaAlias": self.ta_alias,
            "StartDayEt": self.start_day_et.isoformat(),
            "EndDayEt": self.end_day_et.isoformat(),
            "Hours": [h.to_jsonable() for h in self.hours],
        }

    @classmethod
    def from_jsonable(cls, d: dict) -> "HourlyFile":
        return cls(
            ta_alias=d["TaAlias"],
            start_day_et=datetime.date.fromisoformat(d["StartDayEt"]),
            end_day_et=datetime.date.fromisoformat(d["EndDayEt"]),
            hours=[HourRecord.from_jsonable(h) for h in d["Hours"]],
        )

    def path(self, folder: Path) -> Path:
        condition = f"{self.start_day_et:%Y%m%d}.{self.end_day_et:%Y%m%d}"
        return folder / f"{self.ta_alias}-{condition}-hourly.dist.json"

    def write(self, folder: Path) -> Path:
        path = self.path(folder)
        path.write_text(json.dumps(self.to_jsonable(), separators=(",", ":")) + "\n")
        return path

    @classmethod
    def read(cls, path: Path) -> "HourlyFile":
        return cls.from_jsonable(json.loads(path.read_text()))

    def table(self) -> Table:
        """The hours as rows, one per HourRecord, with the hour's start in ET."""
        rows = []
        for h in self.hours:
            d = h.to_jsonable()
            rows.append((datetime.datetime.fromtimestamp(h.hour_start_s, ET).strftime("%Y-%m-%d %H:%M"),
                         h.hour_start_s, d["ValidFraction"], d["FlowingFraction"], d["MeanGpm"],
                         d["SourceF"], d["ReturnF"], d["HeatKwh"]))
        return Table(f"{self.house}-hourly", f"{self.ta_alias}: one row per hour with enough valid samples, {self.start_day_et} to {self.end_day_et}",
                     ("HourStartEt", "HourStartS", "ValidFraction", "FlowingFraction", "MeanGpm", "SourceF", "ReturnF", "HeatKwh"),
                     rows, "emitter_drop.py")


class MinuteColumns(NamedTuple):
    """One house's distribution loop on a minute grid, as columns of
    equal length, one entry per valid minute. A pump column is None
    for a minute its channel had never reported by."""

    minute_start_s: list[UTCSeconds]  # the minute's first second
    gpm: list[float]  # mean distribution flow
    pump_w: list[float | None]  # mean distribution pump power
    pump_v: list[float | None]  # mean commanded pump speed, volts on the 0-10 V output
    source_f: list[float]  # mean source temperature
    return_f: list[float]  # mean return temperature
    temp_age_s: list[float]  # oldest source or return reading used in the minute, seconds
    calls: dict[SpaceheatName, list[float | None]]  # zone white-wire channel -> share of the minute calling

    def to_jsonable(self) -> dict:
        return {
            "MinuteStartS": self.minute_start_s,
            "Gpm": self.gpm,
            "PumpW": self.pump_w,
            "Pump010V": self.pump_v,
            "SourceF": self.source_f,
            "ReturnF": self.return_f,
            "TempAgeS": self.temp_age_s,
            "Calls": self.calls,
        }

    @classmethod
    def from_jsonable(cls, d: dict) -> "MinuteColumns":
        return cls(
            minute_start_s=d["MinuteStartS"],
            gpm=d["Gpm"],
            pump_w=d["PumpW"],
            pump_v=d["Pump010V"],
            source_f=d["SourceF"],
            return_f=d["ReturnF"],
            temp_age_s=d["TempAgeS"],
            calls=d["Calls"],
        )

    @staticmethod
    def concat(parts: list["MinuteColumns"]) -> "MinuteColumns":
        """Weekly parts in time order into one; a zone wire absent from
        a part is None through that part."""
        wires = sorted({n for p in parts for n in p.calls})
        return MinuteColumns(
            minute_start_s=[v for p in parts for v in p.minute_start_s],
            gpm=[v for p in parts for v in p.gpm],
            pump_w=[v for p in parts for v in p.pump_w],
            pump_v=[v for p in parts for v in p.pump_v],
            source_f=[v for p in parts for v in p.source_f],
            return_f=[v for p in parts for v in p.return_f],
            temp_age_s=[v for p in parts for v in p.temp_age_s],
            calls={
                n: [v for p in parts for v in p.calls.get(n, [None] * len(p.minute_start_s))]
                for n in wires
            },
        )

    def arrays(self) -> "MinuteArrays":
        """The same columns as float arrays, None as NaN."""
        def floats(xs: list) -> np.ndarray:
            return np.array([np.nan if v is None else v for v in xs], dtype=np.float64)
        return MinuteArrays(
            minute_start_s=np.array(self.minute_start_s, dtype=np.int64),
            gpm=floats(self.gpm),
            pump_w=floats(self.pump_w),
            pump_v=floats(self.pump_v),
            source_f=floats(self.source_f),
            return_f=floats(self.return_f),
            temp_age_s=floats(self.temp_age_s),
            calls={n: floats(c) for n, c in self.calls.items()},
        )


class MinuteArrays(NamedTuple):
    """MinuteColumns as numpy arrays for analysis; same fields, None
    carried as NaN."""

    minute_start_s: np.ndarray
    gpm: np.ndarray
    pump_w: np.ndarray
    pump_v: np.ndarray
    source_f: np.ndarray
    return_f: np.ndarray
    temp_age_s: np.ndarray
    calls: dict[SpaceheatName, np.ndarray]


class MinuteFile(NamedTuple):
    """`<ta>-<start>.<end>-minute.pump.json`: one house's season of
    minutes. The window is Eastern calendar days, end exclusive."""

    ta_alias: LeftRightDot
    start_day_et: datetime.date
    end_day_et: datetime.date
    minutes: MinuteColumns

    @property
    def house(self) -> str:
        """The house segment of the alias (`beech`)."""
        return self.ta_alias.split(".")[-2]

    def to_jsonable(self) -> dict:
        return {
            "TaAlias": self.ta_alias,
            "StartDayEt": self.start_day_et.isoformat(),
            "EndDayEt": self.end_day_et.isoformat(),
            "Minutes": self.minutes.to_jsonable(),
        }

    @classmethod
    def from_jsonable(cls, d: dict) -> "MinuteFile":
        return cls(
            ta_alias=d["TaAlias"],
            start_day_et=datetime.date.fromisoformat(d["StartDayEt"]),
            end_day_et=datetime.date.fromisoformat(d["EndDayEt"]),
            minutes=MinuteColumns.from_jsonable(d["Minutes"]),
        )

    def path(self, folder: Path) -> Path:
        condition = f"{self.start_day_et:%Y%m%d}.{self.end_day_et:%Y%m%d}"
        return folder / f"{self.ta_alias}-{condition}-minute.pump.json"

    def write(self, folder: Path) -> Path:
        path = self.path(folder)
        path.write_text(json.dumps(self.to_jsonable(), separators=(",", ":")) + "\n")
        return path

    @classmethod
    def read(cls, path: Path) -> "MinuteFile":
        return cls.from_jsonable(json.loads(path.read_text()))

    def table(self) -> Table:
        """The minutes as rows, one per valid minute, a column per zone wire."""
        m = self.minutes
        wires = sorted(m.calls)
        rows = []
        for i, t in enumerate(m.minute_start_s):
            rows.append((datetime.datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d %H:%M"), t, m.gpm[i], m.pump_w[i],
                         m.pump_v[i], m.source_f[i], m.return_f[i], m.temp_age_s[i], *(m.calls[w][i] for w in wires)))
        return Table(f"{self.house}-minute", f"{self.ta_alias}: one row per valid minute, {self.start_day_et} to {self.end_day_et}; the last columns are each zone wire's share of the minute calling",
                     ("MinuteStartEt", "MinuteStartS", "Gpm", "PumpW", "Pump010V", "SourceF", "ReturnF", "TempAgeS", *wires),
                     rows, "pump_speed.py")
