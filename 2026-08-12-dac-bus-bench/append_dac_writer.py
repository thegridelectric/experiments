"""Build the bench-rung layout: the verbatim tlayouts honeysuckle artifact
plus the Dac2 writer component + actor node, constructed through the
gwsproto models so the appended shape is exactly what the gen will emit
once spaceheat.node.gt/304 exists (the published 303 schema pins
gw1.actor.class/012, so the gen cannot emit an I2cDacWriter node yet —
this documented append is the interim; the suite's DAC-writer fixture
appends the identical shape).

Run with the scada venv from this folder:

    ../../gridworks-scada/gw_spaceheat/venv/bin/python append_dac_writer.py

Idempotent: reuses the component/node ids from an existing output file.
"""

import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent.resolve()
SCADA = HERE / "../../gridworks-scada/gw_spaceheat"
sys.path.insert(0, str(SCADA))

from gwsproto.enums import ActorClass, I2cDacChannel  # noqa: E402
from gwsproto.named_types import (  # noqa: E402
    I2cDacChannelConfig,
    I2cDacWriterComponentGt,
    SpaceheatNodeGt,
)

SOURCE = HERE / "../../tlayouts/output/honeysuckle/gw.nolan.layout.json"
OUT = HERE / "gw.nolan.layout.json"
NODE_NAME = "gw108-dac2-writer"
ALIAS = "Gw108 Dac2 Writer"
# mirror the spruce Dac2 EEPROM defaults so the bench is the deployment twin
POWER_ON = [("A", 0), ("B", 0), ("C", 3020), ("D", 0)]


def stable_ids() -> tuple[str, str]:
    if OUT.exists():
        prior = json.loads(OUT.read_text())
        comp = next(
            c
            for c in prior["Components"]
            if c.get("TypeName") == "i2c.dac.writer.component.gt"
        )
        node = next(n for n in prior["ShNodes"] if n["Name"] == NODE_NAME)
        return comp["ComponentId"], node["ShNodeId"]
    return str(uuid.uuid4()), str(uuid.uuid4())


def main() -> None:
    layout = json.loads(SOURCE.read_text())
    board = next(
        c
        for c in layout["Components"]
        if c.get("TypeName") == "scada.board.component.gt"
    )
    component_id, node_id = stable_ids()
    component = I2cDacWriterComponentGt(
        ComponentId=component_id,
        BoardComponentId=board["ComponentId"],
        DacName="Dac2",
        DisplayName=ALIAS,
        ConfigList=[
            I2cDacChannelConfig(
                DacChannel=I2cDacChannel(c),
                PowerOnRawValue=v,
                PowerOnVref="Internal",
                PowerOnGain=1,
            )
            for c, v in POWER_ON
        ],
    )
    node = SpaceheatNodeGt(
        ShNodeId=node_id,
        Name=NODE_NAME,
        ActorHierarchyName=f"s.{NODE_NAME}",
        ActorClass=ActorClass.I2cDacWriter,
        DisplayName=ALIAS,
        ComponentId=component_id,
    )
    layout["Components"].append(
        component.model_dump(by_alias=True, exclude_none=True)
    )
    layout["ShNodes"].append(node.model_dump(by_alias=True, exclude_none=True))
    OUT.write_text(json.dumps(layout, indent=2))
    print(f"wrote {OUT.name}: +component {component_id} +node {NODE_NAME}")


if __name__ == "__main__":
    main()
