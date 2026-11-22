"""Emit the four bench windows as sema instances, one `gw.experiment.run` each.

Window bounds are the README timeline's wall-clock stamps (box clock, ET);
window 1's end is the pico API log's last post. Filenames follow the
instance grammar `<subject>-<condition>-<type.name>-<version>.json`.

    uv run python 2026-11-20-spruce-gw108-revc-bench/emit_instances.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

STAMP = re.compile(r"^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
ET = ZoneInfo("America/New_York")
INSTANCES = HERE / "instances"
SUBJECT = "hw1.isone.me.versant.keene.spruce.scada"
SLUG = "spruce-gw108-revc-bench"


class Window(NamedTuple):
    """One bench window: its condition tag, bounds (ET), code reference and the claim it tested."""

    condition: str
    start: datetime
    end: datetime | None
    code_ref: str
    claim: str


def et(h: int, m: int, s: int = 0) -> datetime:
    return datetime(2026, 11, 20, h, m, s, tzinfo=ET)


def stamp_ms(line: str) -> int | None:
    m = STAMP.match(line)
    if not m:
        return None
    return int(datetime.fromisoformat(m.group(1)).replace(tzinfo=ET).timestamp() * 1000)


def window1_end_ms() -> int:
    ends = [s for s in (stamp_ms(l) for l in (HERE / "evidence" / "pico_api.log").read_text(errors="replace").splitlines()) if s]
    return max(ends)


WINDOWS = [
    Window(
        "window1",
        et(13, 27),
        None,
        "starter-scripts c2021df (jm/gw108-revc) gw108_test_code.py on spruce, scada stopped; runbook.sh steps 1-4",
        "Every Rev C native input, both thermistor ADCs, the CT ADC behind mux channel 4 and the three DACs answer at the pin, bus and address the board-facts spoke states; nothing actuated.",
    ),
    Window(
        "window2",
        et(14, 14),
        et(15, 45),
        "starter-scripts 0b8e836 (jm/gw108-revc) gw108_test_code.py on spruce, scada stopped",
        "Three of four wired zones follow their thermostats on GPIO 17, 27 and 10 and bring distribution flow; all four zone relay pairs run with thermostats idle; with the FCM end of the DB25 on the Rev C pinout and AUX 24 VAC fed, Pump 2, Valve 1, Pump 3 and the heat pump dry contact each drive their load. Upstairs (GPIO 22) never calls, thermostat suspected.",
    ),
    Window(
        "window3",
        et(15, 50),
        et(16, 7),
        "starter-scripts 0b8e836 (jm/gw108-revc) gw108_test_code.py on spruce, scada stopped; evidence/ct-window3 scripts",
        "The secondary pump reaches full speed near 8.5 V on Dac3 channel C (0.2 A at 5 V, 0.6 A at 8.5 V, 0.64 A at full scale); CT1 on the store pump reads on from off cleanly (27 mV RMS at one turn); Valve 2 confirmed across DB25 pins 9 and 22.",
    ),
    Window(
        "window4",
        et(16, 20, 57),
        et(16, 38),
        "gridworks-scada jm/gw108-revc e9bf4a93 with tlayouts c43d091, then 37b18dc (secondary-hx tank module)",
        "Under the scada on the Rev C names every relay spruce drives works: secondary pump relay and 0-10 V, charge valve, store pump, heat pump call through hp-boss with HpDetectedOn and HpDetectedOff closing and opening the secondary pump relay; both boots clean. Open: whether the store pump flows with the iso valve open and the charge valve closed.",
    ),
]


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    for w in WINDOWS:
        end_ms = window1_end_ms() if w.end is None else int(w.end.timestamp() * 1000)
        word = GwExperimentRun(
            experiment_slug=SLUG,
            host_g_node_alias=SUBJECT,
            start_unix_ms=int(w.start.timestamp() * 1000),
            end_unix_ms=end_ms,
            code_ref=w.code_ref,
            verdict=GwExperimentVerdict.Pass,
            claim=w.claim,
        )
        path = INSTANCES / f"{SUBJECT}-{w.condition}-gw.experiment.run-001.json"
        path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
        back = default_codec.from_dict(json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun)
        assert back == word, path
        print(path)


if __name__ == "__main__":
    main()
