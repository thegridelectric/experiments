"""Emit the gw.experiment.run instance for the spruce pico params run.

Start and end are the first and last stamped lines of `timeline.txt` (box
clock, local ET, about 70 seconds behind the laptop clock): the moment the
plant scada was first stopped and the moment it was last confirmed active.

The instance is constructed through the vendored gwexp snapshot class, written
as its dict form, then read back through the codec so the file on disk is what
validates.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

BOX_OFFSET = "-04:00"
START = "2026-09-19T17:35:24"
END = "2026-09-19T17:43:05"


def unix_ms(stamp: str) -> int:
    return int(datetime.fromisoformat(f"{stamp}{BOX_OFFSET}").timestamp() * 1000)


def main() -> None:
    run = GwExperimentRun(
        experiment_slug="spruce-pico-params",
        host_g_node_alias="hw1.isone.me.versant.keene.spruce.scada",
        start_unix_ms=unix_ms(START),
        end_unix_ms=unix_ms(END),
        code_ref="starter-scripts rest_api.py on the box (laptop head 3f0ca48); inline GPIO 23 toggle, no harness file",
    )
    out = HERE / "instances/spruce-gw.experiment.run-000.json"
    out.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
    back = SemaCodec().from_dict(json.loads(out.read_text()), expect=GwExperimentRun)
    print(out.name, back.start_unix_ms, back.end_unix_ms)


if __name__ == "__main__":
    main()
