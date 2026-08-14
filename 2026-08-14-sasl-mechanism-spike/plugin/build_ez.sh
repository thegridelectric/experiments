#!/usr/bin/env bash
# Compile the mechanism INSIDE rabbitmq:4.1-management (erlc ships in the
# image; OTP therefore matches the broker exactly). Output is an UNPACKED
# plugin dir (rabbitmq supports those alongside .ez) that docker-compose
# mounts into /opt/rabbitmq/plugins/. Packing a real .ez is deployment
# work (OPS-496), not spike work.
set -euo pipefail
cd "$(dirname "$0")"

IMG=rabbitmq:4.1-management
APP=rabbitmq_auth_mechanism_gridworks   # plugin/app name (rabbitmq_*)
MOD=rabbit_auth_mechanism_gridworks     # module name (rabbit_*), stock convention
VSN=0.1.0

docker run --rm -v "$PWD":/work -w /work "$IMG" bash -c "
  set -euo pipefail
  DEST=build/${APP}-${VSN}/ebin
  rm -rf build
  mkdir -p \"\$DEST\"
  # -pa the rabbit app's ebin so the behaviour callback check can run;
  # tolerate whatever layout the image uses (unpacked dirs vs .ez).
  PA=''
  for d in /opt/rabbitmq/plugins/rabbit-*/ebin /opt/rabbitmq/ebin; do
    [ -d \"\$d\" ] && PA=\"\$PA -pa \$d\"
  done
  erlc \$PA -o \"\$DEST\" ${MOD}.erl
  cat > \"\$DEST/${APP}.app\" <<EOF
{application, ${APP}, [
  {description, \"GridWorks SASL mechanism: cert identity + claims\"},
  {vsn, \"${VSN}\"},
  {modules, [${MOD}]},
  {registered, []},
  {applications, [kernel, stdlib, rabbit]},
  {env, []}
]}.
EOF
"
echo "built plugin/build/${APP}-${VSN}/ (mounted by docker-compose)"
