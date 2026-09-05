"""Mint the battery's principals on the dev FIS database and print NAME=id
lines (the ids.env the cert generator reads). Idempotent: an existing row is
reused, since a GNode's principal id IS its GNodeId and a cert already cut
for a service id stays valid.

    uv run --project ../../gridworks-fleet-index-service mint.py [--services N]
"""

import argparse
import sys

from fis.db.models import PrincipalKind, PrincipalSql
from fis.db.session import SessionLocal
from fis.principals import create_principal, list_principals

# The dev universe identities the battery speaks as (grid-node-registry
# `seed_dev_universe`, resolved by alias through the gnr façade in setup.sh).
GNODE_ARGS = ("--weather-id", "--scada-id")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather-id", required=True)
    ap.add_argument("--scada-id", required=True)
    ap.add_argument("--ltn-id", required=True)
    ap.add_argument("--services", type=int, default=1, help="storm size")
    args = ap.parse_args()

    with SessionLocal() as s:
        for name, gid in (("weather", args.weather_id), ("scada", args.scada_id), ("ltn", args.ltn_id)):
            if s.get(PrincipalSql, gid) is None:
                create_principal(s, kind=PrincipalKind.GNode, g_node_id=gid, display_name=f"battery {name}")
            print(f"{name}={gid}")

        tag = "battery service"
        have = [p for p in list_principals(s) if (p.display_name or "").startswith(tag)]
        while len(have) < args.services:
            have.append(
                create_principal(s, kind=PrincipalKind.Service, g_node_id=None, display_name=f"{tag} {len(have)}")
            )
        for i, p in enumerate(have[: args.services]):
            print(f"service{i}={p.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
