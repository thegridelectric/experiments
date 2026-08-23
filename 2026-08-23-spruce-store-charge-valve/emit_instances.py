#!/usr/bin/env python3
"""Emit the gw.experiment.run instance for the charge-valve polarity run,
from the driver's results file, THROUGH the vendored snapshot. The per-leg
samples/verdicts stay in the plain results file (kind-specific; no word —
see the driver's Sample note). Byte-stable: ci.sh re-runs this and diffs."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.types import GwExperimentRun  # noqa: E402


def main() -> None:
    r = json.loads((HERE / "charge-valve-polarity-results.json").read_text())
    inst = GwExperimentRun(
        experiment_slug="spruce-store-charge-valve",
        host_g_node_alias="hw1.isone.me.versant.keene.spruce.scada",
        start_unix_ms=r["StartUnixMs"],
        end_unix_ms=r["EndUnixMs"],
        code_ref="charge_valve_polarity.py",
    )
    out_dir = HERE / "instances"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "gw.experiment.run-000.json"
    out.write_text(json.dumps(inst.to_dict(), indent=1) + "\n")
    print(f"wrote {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
