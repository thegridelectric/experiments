#!/usr/bin/env python3
"""Emit the sema-typed instances for the spruce-relay-stress runs.

For every `relay-stress-<run>-results.json` in this folder (the harness's
per-run result file, generated on spruce) emit
`instances/<run>/gw.experiment.run-000.json` — the run's window, host and
code ref — constructed THROUGH the vendored snapshot so schema and axioms
validate at construction. The per-phase reset counts stay in the plain
results file (kind-specific structure; no word — see the harness's
`PhaseResult` note). Byte-stable: `ci.sh` re-runs this and diffs.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.types import GwExperimentRun  # noqa: E402

# The spruce scada GNode (the box the harness ran on). Hand-coded: the
# harness runs on the pi without the snapshot and the deployed layout is not
# fetched here; the same alias the sibling spruce experiments carry.
HOST_G_NODE_ALIAS = "hw1.isone.me.versant.keene.spruce.scada"
SLUG = "spruce-relay-stress"


def run_instance(results_path: Path, code_ref: str) -> GwExperimentRun:
    r = json.loads(results_path.read_text())
    return GwExperimentRun(
        experiment_slug=SLUG,
        host_g_node_alias=HOST_G_NODE_ALIAS,
        start_unix_ms=r["StartUnixMs"],
        end_unix_ms=r["EndUnixMs"],
        code_ref=code_ref,
    )


HARNESSES = {"relay-stress-": "relay_stress.py"}


def main() -> None:
    for prefix, code_ref in HARNESSES.items():
        for results_path in sorted(HERE.glob(f"{prefix}*-results.json")):
            run = results_path.stem.removeprefix(prefix).removesuffix("-results")
            out_dir = HERE / "instances" / run
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / "gw.experiment.run-000.json"
            inst = run_instance(results_path, code_ref)
            out.write_text(json.dumps(inst.to_dict(), indent=1) + "\n")
            print(f"wrote {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
