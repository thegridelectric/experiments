#!/usr/bin/env bash
# The rig's CRL writer: builds the throwaway CA's client-cert revocation
# list into out/crl/<issuer hash>.r0, the hash-dir name Erlang's
# ssl_crl_hash_dir looks up (openssl's -subject_hash of the CA name). The
# broker reads the file at every handshake, so replacing it is live at
# once. Same mechanics as mint-client-cert.py crl against the real CA, on
# throwaway material.
#
#   ./crl.sh                  empty list, valid one year
#   ./crl.sh weather scada    those leaves revoked (by serial), valid one year
#   ./crl.sh --expired ...    same list, nextUpdate one second out: the
#                             expired-CRL case (peer refuses every handshake)
set -euo pipefail
cd "$(dirname "$0")"
OUT=out
CRL=$OUT/crl
mkdir -p "$CRL"
VALIDITY=(-crldays 365)
[ "${1:-}" = "--expired" ] && { VALIDITY=(-crlsec 1); shift; }

# openssl ca's database: one R line per revoked leaf. Only revoked entries
# matter to -gencrl, so the index holds nothing else.
: > "$CRL/index.txt"
[ -f "$CRL/crlnumber" ] || echo 01 > "$CRL/crlnumber"
for name in "$@"; do
  pem=$OUT/$name.pem
  serial=$(openssl x509 -in "$pem" -noout -serial | cut -d= -f2)
  subject=$(openssl x509 -in "$pem" -noout -subject -nameopt RFC2253 | sed 's/^subject=//')
  expiry=$(openssl x509 -in "$pem" -noout -enddate | cut -d= -f2 \
    | python3 -c 'import sys,datetime; print(datetime.datetime.strptime(sys.stdin.read().strip(), "%b %d %H:%M:%S %Y %Z").strftime("%y%m%d%H%M%SZ"))')
  printf 'R\t%s\t%s\t%s\tunknown\t/%s\n' "$expiry" "$(date -u +%y%m%d%H%M%SZ)" "$serial" "$subject" >> "$CRL/index.txt"
done

cat > "$CRL/openssl.cnf" <<CNF
[ca]
default_ca = throwaway
[throwaway]
database    = $CRL/index.txt
crlnumber   = $CRL/crlnumber
certificate = $OUT/ca.pem
private_key = $OUT/ca.key
default_md  = sha256
CNF

hash=$(openssl x509 -in "$OUT/ca.pem" -noout -subject_hash)
openssl ca -config "$CRL/openssl.cnf" -gencrl "${VALIDITY[@]}" -out "$CRL/$hash.r0.tmp" 2>/dev/null
mv "$CRL/$hash.r0.tmp" "$CRL/$hash.r0"   # atomic: the broker never sees a half-written list
echo "$CRL/$hash.r0: revoked=[$*] $(openssl crl -in "$CRL/$hash.r0" -noout -nextupdate)"
