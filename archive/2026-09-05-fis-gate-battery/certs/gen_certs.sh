#!/usr/bin/env bash
# Harness PKI: a throwaway CA + server cert (CN/SAN localhost) + one client
# cert per identity in out/ids.env (CN = the principal id FIS gates on), plus
# a SECOND cert with the same CN for weather and for the scada (weather2,
# scada2): the replaced-pi case, where the predecessor's cert is still valid
# and only the CRL (crl.sh) tells the two apart.
# NOT the GridWorks CA; nothing here leaves the rig. Reads ids.env written by
# ../setup.sh; keeps an existing CA so re-minting a client cert does not
# invalidate the others.
set -euo pipefail
cd "$(dirname "$0")"
OUT=out
mkdir -p "$OUT"
[ -f "$OUT/ids.env" ] || { echo "run ../setup.sh first (writes $OUT/ids.env)"; exit 1; }

if [ ! -f "$OUT/ca.pem" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout "$OUT/ca.key" -out "$OUT/ca.pem" \
    -subj "/CN=FIS-Gate-Battery-Throwaway-CA" 2>/dev/null
  openssl req -newkey rsa:2048 -nodes \
    -keyout "$OUT/server.key" -out "$OUT/server.csr" \
    -subj "/CN=localhost" 2>/dev/null
  openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
    -CAcreateserial -days 365 -out "$OUT/server.pem" \
    -extfile <(printf "subjectAltName=DNS:localhost,DNS:broker") 2>/dev/null
fi

mint() {  # <file name> <CN>; every leaf gets its own serial (-CAcreateserial)
  openssl req -newkey rsa:2048 -nodes \
    -keyout "$OUT/$1.key" -out "$OUT/$1.csr" -subj "/CN=$2" 2>/dev/null
  openssl x509 -req -in "$OUT/$1.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
    -CAcreateserial -days 365 -out "$OUT/$1.pem" 2>/dev/null
  echo "$1 -> CN=$2 serial=$(openssl x509 -in "$OUT/$1.pem" -noout -serial | cut -d= -f2)"
}

# one client cert per NAME=<principal id> line
while IFS='=' read -r name id; do
  [ -z "$name" ] && continue
  mint "$name" "$id"
done < "$OUT/ids.env"

# the same-CN pair: a second cert for the same principal, the replaced pi
for name in weather scada; do
  mint "${name}2" "$(grep "^$name=" "$OUT/ids.env" | cut -d= -f2)"
done

# an empty CRL, so crl_check = peer has a list to read from the first handshake
./crl.sh

chmod 644 "$OUT"/*.key "$OUT"/*.pem   # the broker container reads as non-root
