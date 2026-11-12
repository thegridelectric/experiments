#!/usr/bin/env python3
"""Emit this folder's `gw.experiment.run` through the vendored snapshot:
rung 1, the LTN's bid built from the FLO service's answer on the dev
broker. The window runs from the LTN's request to its bid, ET, as read
from the broker capture.

Filename grammar `<subject>-<condition>-<type.name>-<version>.json`:
subject the orange LTN's alias, condition the claim tested.

  uv run python emit_instances.py
"""

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import default_codec  # noqa: E402
from gwexp.sema.enums import GwExperimentVerdict  # noqa: E402
from gwexp.sema.types import GwExperimentRun  # noqa: E402

LTN = "d1.isone.ct.newhaven.orange1"
ET = ZoneInfo("America/New_York")


def ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=ET).timestamp() * 1000)


def main() -> None:
    run = GwExperimentRun(
        experiment_slug="flo-dev-harness",
        host_g_node_alias=LTN,
        start_unix_ms=ms("2026-11-05 13:50:56"),
        end_unix_ms=ms("2026-11-05 13:50:59.922"),
        code_ref="gridworks-flo main; gridworks-scada jm/flo-over-the-broker (PR 605)",
        verdict=GwExperimentVerdict.Pass,
        claim=(
            "The scada-repo LTN's bid for the 14:00 slot is built from the FLO "
            "service's answer inside the LTN's timeout: request 13:50:56, answer "
            "13:50:59, bid on the broker 13:50:59.922 ET"
        ),
    )
    out_dir = HERE / "instances"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{LTN}-flo.round.trip-gw.experiment.run-001.json"
    path.write_text(json.dumps(run.to_dict(), indent=1) + "\n")
    back = default_codec.from_bytes(path.read_bytes())
    assert back == run, path
    print(f"wrote {path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
