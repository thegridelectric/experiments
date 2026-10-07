"""From the journal DB to natural units on a 10 s grid, for one house
and one window: the step every pull script in this folder shares.

Channel words come from the house's own emitted `layout.lite` at the
end of the window (`pull_readings.fetch_layout_channels`); values come
from `gridworks.readings` (`pull_readings.fetch_readings`) and each
channel is converted by its own word's encoding, never by a unit the
database claims. Readings are reported on change, so `on_grid`
forward-fills each channel onto the grid and returns, beside the
values, how old the reading behind each sample is.
"""

import datetime
from typing import Callable, NamedTuple

import numpy as np

from gwexp.sema.codec import SemaCodec
from gwexp.sema.enums import SpaceheatTelemetryName
from gwexp.sema.property_format import LeftRightDot, SpaceheatName, UTCMilliseconds
from gwexp.sema.types import DataChannelGt, DerivedChannelGt
from pull_readings import ET, fetch_layout_channels, fetch_readings
from unit_encodings import FLOW_TO_GPM, TEMP_TO_F, Encoding, word_encoding

GRID_S = 10  # the grid step
STALE_S = 600  # a temperature channel silent this long makes the sample invalid
CHUNK_DAYS = 7  # one journal query spans this many days; longer hits the statement timeout

# Encodings the shared tables in ../unit_encodings.py do not cover yet;
# keyed by enum member like those tables. They belong there, beside
# TEMP_TO_F and FLOW_TO_GPM, once harmonize-units or the next shared
# edit takes them.
WATTS: dict[Encoding, Callable[[float], float]] = {
    SpaceheatTelemetryName.PowerW: lambda raw: raw,
}
VOLTS: dict[Encoding, Callable[[float], float]] = {
    SpaceheatTelemetryName.VoltsTimesTen: lambda raw: raw / 10,
}


class Pulled(NamedTuple):
    """One house's channel words and raw readings over a window, with
    the grid the readings are placed on. `rows` holds only the channels
    that reported in the window; `words` holds every channel the house
    declared."""

    grid_ms: np.ndarray  # UTC ms, GRID_S apart, start inclusive, end exclusive
    words: dict[SpaceheatName, DataChannelGt | DerivedChannelGt]
    rows: dict[SpaceheatName, list[tuple[UTCMilliseconds, int]]]  # (time, raw value)


def pull(ta: LeftRightDot, names: list[SpaceheatName], likes: list[str],
         start_ms: UTCMilliseconds, end_ms: UTCMilliseconds, codec: SemaCodec) -> Pulled:
    """Words from the layout.lite at-or-before `end_ms`, readings for
    `names` plus every channel matching a SQL LIKE in `likes`."""
    words = fetch_layout_channels(ta, end_ms, codec)
    rows, _ = fetch_readings(ta, names, likes, start_ms, end_ms)
    grid_ms = np.arange(start_ms, end_ms, GRID_S * 1000, dtype=np.int64)
    return Pulled(grid_ms=grid_ms, words=words, rows=rows)


def on_grid(rows: list[tuple[UTCMilliseconds, int]],
            grid_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Forward-fill on-change readings onto the grid: (raw values, age
    of the reading behind each sample in seconds; inf before the first
    reading)."""
    t = np.array([r[0] for r in rows], dtype=np.int64)
    v = np.array([r[1] for r in rows], dtype=np.float64)
    idx = np.searchsorted(t, grid_ms, side="right") - 1
    seen = idx >= 0
    idx = np.clip(idx, 0, None)
    age_s = np.where(seen, (grid_ms - t[idx]) / 1000.0, np.inf)
    return v[idx], age_s


def natural(word: DataChannelGt | DerivedChannelGt, raw: np.ndarray) -> np.ndarray:
    """Raw wire values in the word's natural unit: °F, gpm, W or V,
    chosen by the word's own encoding. Refuses an encoding no table
    covers rather than passing the raw value through."""
    encoding = word_encoding(word)
    for table in (TEMP_TO_F, FLOW_TO_GPM, WATTS, VOLTS):
        if encoding in table:
            return np.vectorize(table[encoding])(raw)
    raise ValueError(f"no natural-unit table for {word.name} encoded {encoding}")


def chunk_edges(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """Day edges that cut [start, end) into CHUNK_DAYS pieces."""
    edges = [start]
    while edges[-1] < end:
        edges.append(min(edges[-1] + datetime.timedelta(days=CHUNK_DAYS), end))
    return edges


def et_midnight_ms(d: datetime.date) -> UTCMilliseconds:
    return int(datetime.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp() * 1000)
