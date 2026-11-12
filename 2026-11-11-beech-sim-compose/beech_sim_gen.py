"""The layout pair of a simulated Beech: the all-sim House0 skeleton that
tlayouts authors for orange, with Beech's two zones, its three 120-gallon
store tanks and a d1 identity of its own.

Run by gen_layout.sh, which puts a tlayouts tree at a pinned commit on the
path and runs this in the scada's environment, where the node and channel
names tlayouts imports live:

    python beech_sim_gen.py <tlayouts tree> <out dir>

Ids are kept across runs: the previous layout in <out dir> is the
generator's reference.
"""

import dataclasses
import json
import sys
from pathlib import Path

TLAYOUTS = Path(sys.argv[1]).resolve()
OUT_DIR = Path(sys.argv[2]).resolve()
sys.path[:0] = [str(TLAYOUTS), str(TLAYOUTS / "src")]

from orange_sim_gen import HOUSE0_SIM  # noqa: E402
from tlayouts.house0_sema_gen import ZoneCircuitSpec, gen_artifacts  # noqa: E402
from tlayouts.sema.codec import default_codec  # noqa: E402

HOUSE = "d1.isone.me.versant.keene.beech"
ZONES = ["down", "up"]

GNODES = [
    {
        "Alias": HOUSE,
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
        "Alias": f"{HOUSE}.ta",
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
        "Alias": f"{HOUSE}.scada",
        "BaseClass": "Logical",
        "DisplayName": "Simulated Beech Scada",
        "GNodeClass": "Scada",
        "GNodeId": "2d9b2b4b-60a5-4680-93bd-626bc78647b0",
        "Status": "Active",
        "TypeName": "g.node.gt",
        "Version": "006",
    },
]

BEECH_SIM = dataclasses.replace(
    HOUSE0_SIM,
    scada_display_name="Simulated Beech Scada",
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

LAYOUT = OUT_DIR / "hardware-layout.json"
PARAMS = OUT_DIR / "operational-params.json"


def main() -> None:
    layout, params = gen_artifacts(BEECH_SIM, LAYOUT if LAYOUT.exists() else None)
    for path, word in ((LAYOUT, layout), (PARAMS, params)):
        as_dict = word.to_dict()
        default_codec.from_dict(as_dict)
        path.write_text(json.dumps(as_dict, indent=2) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
