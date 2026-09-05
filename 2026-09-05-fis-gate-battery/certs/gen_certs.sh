#!/usr/bin/env bash
# Harness PKI: a throwaway CA + server cert (CN/SAN localhost) + one client
# cert per identity in out/ids.env (CN = the principal id FIS gates on).
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

# one client cert per NAME=<principal id> line
while IFS='=' read -r name id; do
  [ -z "$name" ] && continue
  openssl req -newkey rsa:2048 -nodes \
    -keyout "$OUT/$name.key" -out "$OUT/$name.csr" -subj "/CN=$id" 2>/dev/null
  openssl x509 -req -in "$OUT/$name.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
    -CAcreateserial -days 365 -out "$OUT/$name.pem" 2>/dev/null
  echo "$name -> CN=$id"
done < "$OUT/ids.env"

chmod 644 "$OUT"/*.key "$OUT"/*.pem   # the broker container reads as non-root
