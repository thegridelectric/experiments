#!/usr/bin/env python3
"""Emit the gw.experiment.run instance for the maple bring-up window,
THROUGH the vendored snapshot. The window is the pulled readings
instance's own bounds. Findings stay in the README and the defrost
events file (kind-specific; no word)."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import GwExperimentRun, GwReadings  # noqa: E402


def main() -> None:
    pull_path = HERE / "hw1.isone.me.versant.keene.maple.ta-gw.readings-000.json"
    pull = SemaCodec().from_dict(json.loads(pull_path.read_text()), expect=GwReadings)
    inst = GwExperimentRun(
        experiment_slug="maple-starts-heating",
        host_g_node_alias="hw1.isone.me.versant.keene.maple.scada",
        start_unix_ms=pull.start_unix_ms,
        end_unix_ms=pull.end_unix_ms,
        code_ref="defrost_hunt.py",
    )
    out_dir = HERE / "instances"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "gw.experiment.run-000.json"
    out.write_text(json.dumps(inst.to_dict(), indent=1) + "\n")
    print(f"wrote {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
