"""The pod's two houses, from tlayouts' sim output and the registry's export.

beech1 and beech2 are twins: one spec at two aliases, written by tlayouts
as `output/beech1-sim/` and `output/beech2-sim/`. This writes each as a
folder a scada reads:

- `hardware-layout.json`: tlayouts' layout, copied byte for byte.
- `operational-params.json`: tlayouts' params with the house's variant.
  A house whose variant is the one tlayouts wrote is copied byte for
  byte. Otherwise the word is authored again through OperationalParams,
  and the round trip through the wire form validates it.
- `ta-deed.json`: the house's `ta.deed`, a simulated asset attested so
  the scada accepts dispatch.

and, in `flo/`, the `g.node.gt` of the `d1.flo` both LTNs ask, copied
from the registry's export.

Run by houses.sh in the scada's environment at its pinned commit, where
OperationalParams and TaDeed are the classes the pod's scada decodes with:

    python twin_houses.py <tlayouts tree> <registry tree> <out dir>
"""

import json
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

from gwsproto.enums import SeasonalStorageMode, TaValidationState
from gwsproto.named_types import OperationalParams, TaDeed

FLO_EXPORT = "d1.flo-g.node.gt-006.json"

# The deed's attester and issue time are typed here. No export states a
# simulated TerminalAsset's deed; a `ta.deed` per simulated TerminalAsset
# in the registry's dev export retires both constants and `deed`.
VALIDATOR_ALIAS = "d1.validator.gridworks"
DEED_ISSUED_S = 1794852000


class Twin(NamedTuple):
    """One house of the pod: its folder here, tlayouts' output folder and
    the variant it runs."""

    folder: str
    tlayouts_output: str
    storage: SeasonalStorageMode


TWINS = (
    Twin("beech1", "beech1-sim", SeasonalStorageMode.AllTanks),
    Twin("beech2", "beech2-sim", SeasonalStorageMode.BufferOnly),
)


def params_with(source: Path, storage: SeasonalStorageMode) -> bytes:
    """The operational params at `source` with the variant `storage`."""
    raw = source.read_bytes()
    word = OperationalParams.model_validate_json(raw)
    if word.FamilyParams.SeasonalStorageMode == storage:
        return raw
    family = word.FamilyParams.model_copy(update={"SeasonalStorageMode": storage})
    # model_copy does not validate; the round trip through the wire form does.
    authored = OperationalParams.model_validate_json(
        word.model_copy(update={"FamilyParams": family}).model_dump_json(
            by_alias=True, exclude_none=True
        )
    )
    as_dict = json.loads(authored.model_dump_json(by_alias=True, exclude_none=True))
    return (json.dumps(as_dict, indent=2) + "\n").encode()


def deed(layout: Path) -> TaDeed:
    """The deed of the layout's TerminalAsset."""
    (ta,) = [
        g
        for g in json.loads(layout.read_text())["GNodes"]
        if g["GNodeClass"] == "TerminalAsset"
    ]
    return TaDeed(
        TaId=ta["GNodeId"],
        TaAlias=ta["Alias"],
        ValidationState=TaValidationState.ValidatedSimulatedAsset,
        ValidatorAlias=VALIDATOR_ALIAS,
        IssuedS=DEED_ISSUED_S,
    )


def main() -> None:
    tlayouts, registry, out = (Path(arg).resolve() for arg in sys.argv[1:4])
    for twin in TWINS:
        source = tlayouts / "output" / twin.tlayouts_output
        folder = out / twin.folder
        folder.mkdir(parents=True, exist_ok=True)
        layout = folder / "hardware-layout.json"
        shutil.copyfile(source / "gw.house0.layout.json", layout)
        (folder / "operational-params.json").write_bytes(
            params_with(source / "gw.house0.operational.params.json", twin.storage)
        )
        (folder / "ta-deed.json").write_text(deed(layout).model_dump_json(indent=2) + "\n")
    (out / "flo").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(registry / "dev-universe" / FLO_EXPORT, out / "flo" / "g.node.gt.json")


if __name__ == "__main__":
    main()
