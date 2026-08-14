#!/usr/bin/env bash
# Test PKI for the spike: throwaway CA + server cert (CN/SAN localhost) +
# client cert whose CN is a fake GNodeId — the identity the mechanism must
# surface as the username. NOT the GridWorks CA; nothing here leaves the rig.
set -euo pipefail
cd "$(dirname "$0")"

FAKE_GNODE_ID="7b0788aa-27c5-4a3f-9d5c-6f9a3e2b1c4d"
OUT=out
rm -rf "$OUT"; mkdir -p "$OUT"

# CA
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout "$OUT/ca.key" -out "$OUT/ca.pem" \
  -subj "/CN=Spike-Throwaway-CA" 2>/dev/null

# Server (SAN required by modern clients)
openssl req -newkey rsa:2048 -nodes \
  -keyout "$OUT/server.key" -out "$OUT/server.csr" \
  -subj "/CN=localhost" 2>/dev/null
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
  -CAcreateserial -days 30 -out "$OUT/server.pem" \
  -extfile <(printf "subjectAltName=DNS:localhost,DNS:broker") 2>/dev/null

# Client: CN = the fake GNodeId
openssl req -newkey rsa:2048 -nodes \
  -keyout "$OUT/client.key" -out "$OUT/client.csr" \
  -subj "/CN=${FAKE_GNODE_ID}" 2>/dev/null
openssl x509 -req -in "$OUT/client.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
  -CAcreateserial -days 30 -out "$OUT/client.pem" 2>/dev/null

chmod 644 "$OUT"/*.key "$OUT"/*.pem   # broker container reads as non-root
echo "certs in certs/out/; client CN = ${FAKE_GNODE_ID}"
