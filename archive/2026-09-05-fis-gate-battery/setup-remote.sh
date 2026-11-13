#!/usr/bin/env bash
# One-time (idempotent) remote-rig setup, from a laptop checkout: the battery
# identities' principal rows minted on the box with the registry's ids, one
# client cert per identity cut on certbot against the real CA and brought
# here (then removed from certbot), the CA's public cert beside them.
# Reads remote.env; writes $BATTERY_CERTS_DIR/{ids.env,ca.pem,<name>.pem,<name>.key}.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./remote.env; set +a
STORM=${STORM:-100}
OUT=$BATTERY_CERTS_DIR
mkdir -p "$OUT"

id_of() { curl -sf "$BATTERY_GNR_URL/gnr/g-node-by-alias/$1" | python3 -c 'import sys,json; print(json.load(sys.stdin)["GNodeId"])'; }
WEATHER=$(id_of "$BATTERY_WEATHER_ALIAS")
SCADA=$(id_of "$BATTERY_SCADA_ALIAS")
LTN=$(id_of "$BATTERY_LTN_ALIAS")

# Principals on the box's FIS, through its own CLI (a GNode's principal id IS
# its GNodeId; a service principal is minted once and its id reused, since a
# cert already cut for it stays valid). Nothing lands in the checkout.
ssh "$BATTERY_FIS_LOGIN" bash -s -- "$BATTERY_FIS_CHECKOUT" "$WEATHER" "$SCADA" "$LTN" "$STORM" > "$OUT/ids.env" <<'REMOTE'
set -euo pipefail
cd "$1"; FIS=.venv/bin/fis
have=$($FIS principal list)
gnode() {  # name id
  echo "$have" | grep -q "^$2 " || $FIS principal create --kind GNode --g-node-id "$2" --display-name "battery $1" >/dev/null 2>&1
  echo "$1=$2"
}
gnode weather "$2"; gnode scada "$3"; gnode ltn "$4"
n=$(echo "$have" | grep -c "battery service" || true)
while [ "$n" -lt "$5" ]; do
  $FIS principal create --kind Service --display-name "battery service $n" >/dev/null 2>&1; n=$((n+1))
done
$FIS principal list | grep "battery service" | head -n "$5" | awk '{print "service" NR-1 "=" $1}'
REMOTE
# never minted: the unknown-principal case
echo "unknown=$(python3 -c 'import uuid; print(uuid.uuid4())')" >> "$OUT/ids.env"

# Client certs on certbot: CN = principal id, key dir battery-<box>-<name>;
# the material streams back as a tar and the dirs are removed from certbot
# (the battery's identities are ephemeral; nothing of theirs stays there).
BOX=${BATTERY_BROKER_HOST%%.*}
ssh "$BATTERY_CERTBOT" bash -s -- "$BOX" < <(cat <<EOS
set -euo pipefail
T=\$(mktemp -d)
cd ~/.local/share/gridworks/ca/certs
while IFS='=' read -r name id; do
  [ -z "\$name" ] && continue
  ~/.local/bin/gwcert key add --common-name "\$id" --valid-days 90 "battery-\$1-\$name" >/dev/null 2>&1
  cp "battery-\$1-\$name/battery-\$1-\$name.crt" "\$T/\$name.pem"
  cp "battery-\$1-\$name/private/battery-\$1-\$name.pem" "\$T/\$name.key"
  rm -rf "battery-\$1-\$name"
done <<'IDS'
$(cat "$OUT/ids.env")
IDS
cd "\$T" && tar cf - . && cd / && rm -rf "\$T"
EOS
) | tar xf - -C "$OUT"
cp ../../gridworks-infra/authority/ca.crt "$OUT/ca.pem"
chmod 600 "$OUT"/*.key
echo "ids in $OUT/ids.env; $(wc -l < "$OUT/ids.env") identities; certs from certbot against the real CA"
