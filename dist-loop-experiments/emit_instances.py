#!/usr/bin/env python3
"""Emit this folder's `gw.experiment.run` instances THROUGH the vendored
snapshot, one per house and tested claim, each stamped with its
verdict. The window is the one the house's hourly file states (the
minute pull covers the same window). The findings themselves stay in
the output files and the hourly and minute files (kind-specific; no
word yet).

Filename grammar `<subject>-<condition>-<type.name>-<version>.json`:
subject the house's scada alias, condition the claim tested.

  uv run python emit_instances.py
"""

import json
import sys
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from grid import et_midnight_ms  # noqa: E402
from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.property_format import LeftRightDot  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402
from houses import ZONE_PAIRS, hourly_files  # noqa: E402

PAPER = "heating-system-design/mix-or-not.md"


class Tested(NamedTuple):
    """One claim this folder tests, with the verdict every house gave
    and the script whose output carries it."""

    condition: LeftRightDot  # the filename's condition field
    claim: str
    code_ref: str
    verdict: GwExperimentVerdict


HOURLY_CLAIMS = [
    Tested("claim2", f'{PAPER} claims register, claim 2: a steady-state emitter '
                     f'temperature drop of about 20 °F (steady-drop.txt)',
           "emitter_drop.py; steady_drop.py", GwExperimentVerdict.Fail),
    Tested("claim3", f'{PAPER} claims register, claim 3: shorter heat calls return '
                     f'colder water (return-temp.md)',
           "emitter_drop.py; return_temp.py", GwExperimentVerdict.Pass),
]
MINUTE_CLAIMS = [
    Tested("cold.zone.call", "heating-system-design/cold-zone-call-during-steady-heating-memo.md: "
                             "a call from an idle zone during a steady call puts the idle loop's "
                             "cold water through the return, the heat pump and the source "
                             "(beech-bolus-recovery.txt)",
           "pump_speed.py; bolus_recovery.py", GwExperimentVerdict.Pass),
    Tested("cold.zone.call.recovery", "heating-system-design/cold-zone-call-during-steady-heating-memo.md: "
                                      "the source-to-return drop is back near its pre-call value within "
                                      "five minutes of the call ending and its movement 10 to 30 minutes "
                                      "out matches steady-call minutes with no idle-zone call "
                                      "(beech-bolus-recovery.txt)",
           "pump_speed.py; bolus_recovery.py", GwExperimentVerdict.Pass),
]


def write(path: Path, word: GwExperimentRun) -> None:
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_bytes(path.read_bytes())
    assert back == word, path
    print(f"wrote {path.relative_to(HERE)}")


def main() -> None:
    out_dir = HERE / "instances"
    out_dir.mkdir(exist_ok=True)
    for f in hourly_files():
        scada = f.ta_alias.removesuffix(".ta") + ".scada"
        tested = HOURLY_CLAIMS + (MINUTE_CLAIMS if f.house in ZONE_PAIRS else [])
        for t in tested:
            write(out_dir / f"{scada}-{t.condition}-gw.experiment.run-001.json",
                  GwExperimentRun(
                      experiment_slug="dist-loop-experiments", host_g_node_alias=scada,
                      start_unix_ms=et_midnight_ms(f.start_day_et),
                      end_unix_ms=et_midnight_ms(f.end_day_et),
                      code_ref=t.code_ref, verdict=t.verdict, claim=t.claim))


if __name__ == "__main__":
    main()
