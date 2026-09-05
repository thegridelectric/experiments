#!/usr/bin/env bash
# One-time (idempotent) rig setup: principals on the dev FIS db, identity
# files from the registry, client certs. Needs the local gnr façade (:8000)
# and fis-postgres (:5437, migrated to head).
set -euo pipefail
cd "$(dirname "$0")"
FIS=../../gridworks-fleet-index-service
GNR=http://localhost:8000
STORM=${STORM:-100}

curl -sf "$GNR/gnr/g-node-by-alias/d1.isone.me.weather" >/dev/null \
  || { echo "gnr façade not answering on $GNR — start it: (cd ../../grid-node-registry && uv run gnr api)"; exit 1; }

mkdir -p certs/out g_node
id_of() { curl -sf "$GNR/gnr/g-node-by-alias/$1" | python3 -c 'import sys,json; print(json.load(sys.stdin)["GNodeId"])'; }
WEATHER=$(id_of d1.isone.me.weather)
SCADA=$(id_of d1.isone.me.versant.keene.sub.beech.scada)
LTN=$(id_of d1.isone.me.versant.keene.sub.beech)
# the honest GridworksActor leg loads its g.node.gt from disk
curl -sf "$GNR/gnr/g-node-by-id/$WEATHER" > g_node/weather.json

uv run --project "$FIS" mint.py --weather-id "$WEATHER" --scada-id "$SCADA" --ltn-id "$LTN" --services "$STORM" > certs/out/ids.env
# never minted: the unknown-principal case
echo "unknown=$(python3 -c 'import uuid; print(uuid.uuid4())')" >> certs/out/ids.env
./certs/gen_certs.sh | tail -3
echo "ids in certs/out/ids.env; $(wc -l < certs/out/ids.env) identities"
