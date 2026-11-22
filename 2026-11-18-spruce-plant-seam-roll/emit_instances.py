"""Emit the roll window as a sema instance, one `gw.experiment.run`.

Bounds are the README timeline (laptop clock, ET): the LTN restart on
`jm/plant-seam` at 19:14:46 to spruce's restart on the merged main at
20:00:01.

    uv run python 2026-11-18-spruce-plant-seam-roll/emit_instances.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

ET = ZoneInfo("America/New_York")
INSTANCES = HERE / "instances"
SUBJECT = "hw1.isone.me.versant.keene.spruce.scada"
CODE_REF = "gridworks-scada jm/plant-seam 72c00fa3 (PR 630) from main 7e8e52f4; merged as 2b2028f0; tlayouts main pair"
CLAIM = (
    "The plant seam (PR 630) runs on a real box with no device-path glitch: clean boot on spruce, "
    "the fleet's one GPIO relay actuated twice under the pico cycler with the picos rebooting each time, "
    "every relay and power channel reporting with pre-roll values, for 45 minutes before the merged main."
)


def main() -> None:
    INSTANCES.mkdir(exist_ok=True)
    word = GwExperimentRun(
        experiment_slug="spruce-plant-seam-roll",
        host_g_node_alias=SUBJECT,
        start_unix_ms=int(datetime(2026, 11, 18, 19, 14, 46, tzinfo=ET).timestamp() * 1000),
        end_unix_ms=int(datetime(2026, 11, 18, 20, 0, 1, tzinfo=ET).timestamp() * 1000),
        code_ref=CODE_REF,
        verdict=GwExperimentVerdict.Pass,
        claim=CLAIM,
    )
    path = INSTANCES / f"{SUBJECT}-gw.experiment.run-001.json"
    path.write_text(json.dumps(word.to_dict(), indent=1) + "\n")
    back = default_codec.from_dict(json.loads(path.read_text()), auto_upgrade=False, expect=GwExperimentRun)
    assert back == word, path
    print(path)


if __name__ == "__main__":
    main()
