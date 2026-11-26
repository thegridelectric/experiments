"""The layout pair of a simulated Beech: the all-sim House0 skeleton that
tlayouts authors for orange, with Beech's two zones, its three 120-gallon
store tanks and a d1 identity of its own. Every sensing component is one
the plant shows, so no pico posts: the web server the word requires is
kept and does not serve.

Beside the pair it writes the house's ta.deed, a simulated asset attested
so the scada accepts dispatch, and, in a flo folder next to <out dir>, the
g.node.gt of the d1.flo the house's LTN asks. The operational params name
the dev-universe Keene maker, the market maker the pod runs.

Run by gen_layout.sh, which puts a tlayouts tree at a pinned commit on the
path and runs this in the scada's environment, where the node and channel
names tlayouts imports live:

    python beech_sim_gen.py <tlayouts tree> <out dir> [<house alias> [<storage>]]

`<house alias>` defaults to `d1.isone.me.versant.keene.beech.at`.
`<storage>` is `AllTanks` or `BufferOnly` and defaults to `AllTanks`.
Ids are kept across runs: the previous layout in <out dir> is the
generator's reference. Aliases follow the house argument.
"""

import dataclasses
import json
import sys
import uuid
from pathlib import Path

TLAYOUTS = Path(sys.argv[1]).resolve()
OUT_DIR = Path(sys.argv[2]).resolve()
HOUSE = (
    sys.argv[3] if len(sys.argv) > 3 else "d1.isone.me.versant.keene.beech.at"
)
STORAGE = sys.argv[4] if len(sys.argv) > 4 else "AllTanks"
if STORAGE not in ("AllTanks", "BufferOnly"):
    raise SystemExit(f"storage must be AllTanks or BufferOnly, not {STORAGE!r}")
sys.path[:0] = [str(TLAYOUTS), str(TLAYOUTS / "src")]

from gwsproto.enums import TaValidationState  # noqa: E402
from gwsproto.named_types import TaDeed  # noqa: E402
from orange_sim_gen import HOUSE0_SIM  # noqa: E402
from tlayouts.house0_sema_gen import ZoneCircuitSpec, gen_artifacts  # noqa: E402
from tlayouts.sema.codec import default_codec  # noqa: E402
from tlayouts.sema.enums.base_g_node_class import BaseGNodeClass  # noqa: E402
from tlayouts.sema.enums.g_node_status import GNodeStatus  # noqa: E402
from tlayouts.sema.types.g_node_gt import GNodeGt  # noqa: E402
from tlayouts.sema.types.web_server_component_gt import WebServerComponentGt  # noqa: E402

MAKER = "d1.isone.me.versant.keene"
ZONES = ["down", "up"]
BEECH_AT = "d1.isone.me.versant.keene.beech.at"
LABEL = "BufferOnly" if STORAGE == "BufferOnly" else "AllTanks"
SHORT = "beech-buf" if STORAGE == "BufferOnly" else "beech-at"
_ALIAS = {
    "LeafTransactiveNode": lambda house: house,
    "TerminalAsset": lambda house: f"{house}.ta",
    "Scada": lambda house: f"{house}.scada",
}
_DISPLAY = {
    "LeafTransactiveNode": "LeafTransactiveNode",
    "TerminalAsset": "TerminalAsset",
    "Scada": "Scada",
}

LAYOUT = OUT_DIR / "hardware-layout.json"
PARAMS = OUT_DIR / "operational-params.json"
DEED = OUT_DIR / "ta-deed.json"
FLO_G_NODE = OUT_DIR.parent / "flo" / "g.node.gt.json"

BEECH_GNODES = [
    {
        "Alias": BEECH_AT,
        "BaseClass": "LeafTransactiveNode",
        "DisplayName": "Simulated Beech LeafTransactiveNode",
        "GNodeClass": "LeafTransactiveNode",
        "GNodeId": "13734431-7344-4fd7-bab4-6b6e82cdac35",
        "PositionPointId": "7ab2c253-e653-4bd3-b761-6a4679633bb2",
        "Status": "Active",
        "TypeName": "g.node.gt",
        "Version": "006",
    },
    {
        "Alias": f"{BEECH_AT}.ta",
        "BaseClass": "TerminalAsset",
        "DisplayName": "Simulated Beech TerminalAsset",
        "GNodeClass": "TerminalAsset",
        "GNodeId": "ddc7b6cc-c149-43a2-abed-318a28e240d0",
        "PositionPointId": "7ab2c253-e653-4bd3-b761-6a4679633bb2",
        "Status": "Active",
        "TypeName": "g.node.gt",
        "Version": "006",
    },
    {
        "Alias": f"{BEECH_AT}.scada",
        "BaseClass": "Logical",
        "DisplayName": "Simulated Beech Scada",
        "GNodeClass": "Scada",
        "GNodeId": "2d9b2b4b-60a5-4680-93bd-626bc78647b0",
        "Status": "Active",
        "TypeName": "g.node.gt",
        "Version": "006",
    },
]


def display_name(cls: str) -> str:
    if cls == "TerminalAsset":
        return SHORT
    return f"{SHORT} {_DISPLAY[cls]}"


def mint_gnodes(house: str) -> list[dict]:
    point = str(uuid.uuid4())
    return [
        {
            "Alias": house,
            "BaseClass": "LeafTransactiveNode",
            "DisplayName": display_name("LeafTransactiveNode"),
            "GNodeClass": "LeafTransactiveNode",
            "GNodeId": str(uuid.uuid4()),
            "PositionPointId": point,
            "Status": "Active",
            "TypeName": "g.node.gt",
            "Version": "006",
        },
        {
            "Alias": f"{house}.ta",
            "BaseClass": "TerminalAsset",
            "DisplayName": display_name("TerminalAsset"),
            "GNodeClass": "TerminalAsset",
            "GNodeId": str(uuid.uuid4()),
            "PositionPointId": point,
            "Status": "Active",
            "TypeName": "g.node.gt",
            "Version": "006",
        },
        {
            "Alias": f"{house}.scada",
            "BaseClass": "Logical",
            "DisplayName": display_name("Scada"),
            "GNodeClass": "Scada",
            "GNodeId": str(uuid.uuid4()),
            "Status": "Active",
            "TypeName": "g.node.gt",
            "Version": "006",
        },
    ]


def with_house(nodes: list[dict], house: str) -> list[dict]:
    """Keep ids; point aliases and display names at this house."""
    out: list[dict] = []
    for node in nodes:
        g_node = dict(node)
        cls = g_node["GNodeClass"]
        g_node["Alias"] = _ALIAS[cls](house)
        g_node["DisplayName"] = display_name(cls)
        out.append(g_node)
    return out


def gnodes() -> list[dict]:
    if LAYOUT.exists():
        return with_house(json.loads(LAYOUT.read_text())["GNodes"], HOUSE)
    if HOUSE == BEECH_AT:
        return with_house(BEECH_GNODES, HOUSE)
    return mint_gnodes(HOUSE)


GNODES = gnodes()

BEECH_SIM = dataclasses.replace(
    HOUSE0_SIM,
    scada_display_name=next(
        g["DisplayName"] for g in GNODES if g["GNodeClass"] == "Scada"
    ),
    zone_list=ZONES,
    critical_zone_list=ZONES,
    zone_kwh_per_deg_f_list=[1, 0],
    total_store_tanks=3,
    zone_circuits=[
        dataclasses.replace(HOUSE0_SIM.zone_circuits[0], zone=zone) for zone in ZONES
    ],
    rolling_dist_energy=True,
    minted_gnodes=GNODES,
)
assert all(isinstance(c, ZoneCircuitSpec) for c in BEECH_SIM.zone_circuits)

_TA = next(g for g in GNODES if g["GNodeClass"] == "TerminalAsset")
TA_DEED = TaDeed(
    TaId=_TA["GNodeId"],
    TaAlias=_TA["Alias"],
    ValidationState=TaValidationState.ValidatedSimulatedAsset,
    ValidatorAlias="d1.validator.gridworks",
    IssuedS=1794852000,
)

# The GNodeId grid-node-registry's dev universe gives d1.flo.
FLO = GNodeGt(
    g_node_id="87f059f6-aeb2-4e85-ab17-0fa49995a3ef",
    alias="d1.flo",
    base_class=BaseGNodeClass.Logical,
    g_node_class="Flo",
    status=GNodeStatus.Active,
    display_name="Simulated FLO",
)


def unserved(layout):
    """The layout with every web server set not to serve."""
    components = [
        c.model_copy(
            update={"web_server": c.web_server.model_copy(update={"serve": False})}
        )
        if isinstance(c, WebServerComponentGt)
        else c
        for c in layout.components
    ]
    return layout.model_copy(update={"components": components})


def main() -> None:
    layout, params = gen_artifacts(BEECH_SIM, LAYOUT if LAYOUT.exists() else None)
    layout = unserved(layout)
    for path, word in ((LAYOUT, layout), (PARAMS, params)):
        as_dict = word.to_dict()
        if path == PARAMS:
            as_dict["MarketMakerAlias"] = MAKER
            as_dict["FamilyParams"]["SeasonalStorageMode"] = STORAGE
        default_codec.from_dict(as_dict)
        path.write_text(json.dumps(as_dict, indent=2) + "\n")
        print(f"wrote {path}")
    DEED.write_text(TA_DEED.model_dump_json(indent=2) + "\n")
    print(f"wrote {DEED}")
    flo = FLO.to_dict()
    default_codec.from_dict(flo)
    FLO_G_NODE.parent.mkdir(exist_ok=True)
    FLO_G_NODE.write_text(json.dumps(flo, indent=2) + "\n")
    print(f"wrote {FLO_G_NODE}")


if __name__ == "__main__":
    main()
