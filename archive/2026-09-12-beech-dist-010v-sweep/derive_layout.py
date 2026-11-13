#!/usr/bin/env python3
"""Derive beech's WINDOW layout pair for the dist-010v sweep.

The krida witness rung's derivation (`../2026-09-10-beech-krida-witness/
derive_beech_layout.py`) applied to the scada House0 fixture pair as it
stands after the per-output 0-10V move (each `*-010v` node on an
`i2c.dac.output.component.gt` against the Krida record's two GP8403
entries at 94 and 95, the multiplexer gone), then one more step this
rung needs: the ops word's `ZeroTenPowerOnList` takes beech's DEPLOYED
power-on levels (the deployed layout's `dfr.config` InitialVoltsTimes100,
read off the box 2026-09-12: dist 35, primary 62, store 65) instead of
the fixture's orange1 values, so the window's outputs boot to what
beech's pumps run at today and the sweep's restore level is beech's.

    python3 derive_layout.py [fixture_dir] [out_dir]
"""

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KRIDA_DERIVE = HERE.parent / "2026-09-10-beech-krida-witness" / "derive_beech_layout.py"
FIXTURE_DIR = HERE.parents[1] / "gridworks-scada" / "tests" / "config"
OUT_DIR = HERE / "instances"
LAYOUT_FILE = "beech-window-gw.house0.layout-000.json"
OPS_FILE = "beech-window-gw.house0.operational.params-000.json"

# beech's deployed dfr.config InitialVoltsTimes100 (misnamed: volts times
# ten), node -> level. The one fact this rung adds to the krida derivation.
BEECH_POWER_ON = {"dist-010v": 35, "primary-010v": 62, "store-010v": 65}


def load_krida_derive():
    spec = importlib.util.spec_from_file_location("derive_beech_layout", KRIDA_DERIVE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    fixture_dir = Path(argv[0]) if argv else FIXTURE_DIR
    out_dir = Path(argv[1]) if len(argv) > 1 else OUT_DIR
    krida = load_krida_derive()
    layout = json.loads((fixture_dir / "gw.house0.layout.json").read_text())
    ops = json.loads((fixture_dir / "gw.house0.operational.params.json").read_text())
    layout, ops, id_subs = krida.derive(layout, ops)
    dac_outputs = {
        c["ConfigList"][0]["ActorName"]
        for c in layout["Components"]
        if c["TypeName"] == "i2c.dac.output.component.gt"
    }
    if dac_outputs != set(BEECH_POWER_ON):
        raise SystemExit(f"fixture DAC outputs {sorted(dac_outputs)} != beech's {sorted(BEECH_POWER_ON)}")
    for entry in ops["ZeroTenPowerOnList"]:
        entry["PowerOnVoltsTimesTen"] = BEECH_POWER_ON[entry["NodeName"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / LAYOUT_FILE).write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n")
    (out_dir / OPS_FILE).write_text(json.dumps(ops, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out_dir}/{LAYOUT_FILE} + {OPS_FILE}; {len(id_subs)} zone-private ids remapped; power-on {BEECH_POWER_ON}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
