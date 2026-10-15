#!/usr/bin/env python3
"""Emit this folder's `gw.experiment.run` instances through the vendored
snapshot, one per tested claim, stamped with its verdict. The numbers
behind each verdict are in the workbook (`sheets.py` regenerates it).

Filename grammar `<subject>-<condition>-<type.name>-<version>.json`:
subject spruce's scada alias, condition the claim tested.

  uv run python emit_instances.py
"""

import datetime as dt
import json
import sys
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.property_format import LeftRightDot  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

SCADA = "hw1.isone.me.versant.keene.spruce.scada"
ET = ZoneInfo("America/New_York")


class Tested(NamedTuple):
    """One claim this folder tests: the filename's condition field, the
    claim, the window (ET), the code whose output decides it, the verdict."""

    condition: LeftRightDot
    claim: str
    start: str
    end: str
    code_ref: str
    verdict: GwExperimentVerdict


CLAIMS = [
    Tested("floor.to.room.coefficient",
           "The living room slab's floor-to-room conductance G, referenced to the floor "
           "sensor at tubing depth, is 0.220 kW per F with a floor heat capacity C of "
           "2.3 kWh per F, fitted jointly by least squares over the living-room-only "
           "charge and the free float, RMS 0.45 F; at an assumed 650 sq ft that is "
           "1.15 BTU/h per sq ft per F, inside the whiteboard prior of 2 (or 1) "
           "(spruce-radiant-slab.xlsx, Fit)",
           "2026-10-07 02:00", "2026-10-08 12:00", "sheets.py", GwExperimentVerdict.Pass),
]


def ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=ET).timestamp() * 1000)


def write(path: Path, word: GwExperimentRun) -> None:
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_bytes(path.read_bytes())
    assert back == word, path
    print(f"wrote {path.relative_to(HERE)}")


def main() -> None:
    out_dir = HERE / "instances"
    out_dir.mkdir(exist_ok=True)
    for t in CLAIMS:
        write(out_dir / f"{SCADA}-{t.condition}-gw.experiment.run-001.json",
              GwExperimentRun(experiment_slug="spruce-radiant-slab", host_g_node_alias=SCADA,
                              start_unix_ms=ms(t.start), end_unix_ms=ms(t.end),
                              code_ref=t.code_ref, verdict=t.verdict, claim=t.claim))


if __name__ == "__main__":
    main()
