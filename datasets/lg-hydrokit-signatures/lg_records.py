"""The three data files this folder commits, as typed records: the
compressor runs, the idle episodes of the outdoor unit's 200 W state,
and the mid-run indoor-compressor dips (defrosts and stops) of one
house over the window.

No sema word holds a run, an episode or a dip reduced from channel
readings; a word for a heat pump operating interval (start, end, kind,
per-channel summaries) retires all three files and this module. The
dict form appears only at the read/write boundary (`write` / `read`),
keyed in PascalCase like sema's wire form.

Unfinished: no file has been written or read through it yet.
"""

import json
from pathlib import Path
from typing import NamedTuple, TypeVar

from gwexp.sema.property_format import UTCSeconds
from lg_common import END, START, ta_alias


class Run(NamedTuple):
    """One compressor run: on after 30 s over 2000 W, off after 60 s
    under 350 W on hp-odu-pwr. Steady figures are medians over the
    10 s grid from 15 min after the start to 1 min before the end; NaN
    for a run too short to have that stretch."""

    start_s: UTCSeconds
    dur_s: int
    r6_at_start: float  # relay 6 on the grid at the start; 0 is commanded on
    odu_med_w: float
    odu_p10_w: float
    odu_p90_w: float
    idu_med_w: float
    flow_med_gpm: float
    lift_med_f: float
    lwt_med_f: float
    ewt_med_f: float
    foat_med_f: float
    odu_reports_steady: int  # raw hp-odu-pwr reports inside the steady stretch
    idu_lag_s: float  # hp-idu-pwr first over 1500 W after hp-odu-pwr first over 2000 W; NaN if not within 15 min


class IdleEpisode(NamedTuple):
    """Consecutive raw hp-odu-pwr reports at 150-260 W outside any run.
    The state began between prev_out_s and first_s and ended between
    last_s and next_out_s (the reports either side of it)."""

    first_s: UTCSeconds
    last_s: UTCSeconds
    prev_out_s: UTCSeconds
    next_out_s: UTCSeconds
    prev_kind: str  # the report before: standby (under 60 W), run, other
    next_kind: str
    reports: int
    level_w: float  # median of the episode's reports
    since_stop_s: float  # first_s minus the end of the last run; NaN before the first
    to_next_start_s: float  # start of the next run minus last_s; NaN after the last
    foat_f: float  # forecast at first_s, NaN if none within 2 h
    r6: float  # relay 6 at first_s


class Dip(NamedTuple):
    """Relay 6 closed, 15 min or more into a run, hp-odu-pwr over 5 kW
    in the 5 min before: hp-idu-pwr under 800 W for at most 30 min and
    the sum back over 9 kW within 40 min. A defrost keeps hp-odu-pwr at
    or over 350 W throughout; a stop does not. Begins at the last
    hp-odu-pwr sample over 5 kW, ends at the sum back over 9 kW."""

    start_s: UTCSeconds
    kind: str  # defrost or stop
    total_s: int
    fall_to_idu_off_s: int
    idu_off_s: int
    sum_under_8400_s: int
    odu_min_w: float
    odu_med_w: float
    idu_max_before_w: float
    lift_pre_f: float
    lift_min_f: float
    lwt_pre_f: float
    lwt_max_pre_f: float
    lwt_min_f: float
    flow_min_gpm: float
    flow_med_gpm: float
    foat_f: float
    since_start_s: float


R = TypeVar("R", Run, IdleEpisode, Dip)
KIND = {Run: "lg.runs", IdleEpisode: "lg.idle.episodes", Dip: "lg.dips"}


def path_for(house: str, record: type[NamedTuple]) -> Path:
    here = Path(__file__).parent
    return here / f"{ta_alias(house)}-{START:%Y%m%d}.{END:%Y%m%d}-{KIND[record]}.json"


def pascal(field: str) -> str:
    return "".join(p.capitalize() for p in field.split("_"))


def write(house: str, record: type[R], rows: list[R]) -> Path:
    """One house's records to its committed file; NaN written as null."""
    def cell(v: object) -> object:
        if isinstance(v, float):
            return None if v != v else round(v, 2)
        return v
    body = {
        "TerminalAssetAlias": ta_alias(house),
        "Start": START.isoformat(),
        "End": END.isoformat(),
        "Records": [{pascal(k): cell(v) for k, v in r._asdict().items()} for r in rows],
    }
    p = path_for(house, record)
    p.write_text(json.dumps(body, indent=0) + "\n")
    return p


def read(house: str, record: type[R]) -> list[R]:
    """One house's committed file back as records; null read as NaN."""
    body = json.loads(path_for(house, record).read_text())
    out: list[R] = []
    for d in body["Records"]:
        vals = [d[pascal(f)] for f in record._fields]
        out.append(record._make(float("nan") if v is None else v for v in vals))
    return out
