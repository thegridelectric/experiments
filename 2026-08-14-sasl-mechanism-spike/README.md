# SASL mechanism spike — claims through a stock 4.1 broker to a stub FIS

OPS-496 first deliverable (the mTLS+FIS design's first experiment, OPS-420):
prove that a client cert + a `fis.connect.claims`-shaped payload in the SASL
response arrive at the auth backend's `user_path` as `username` (from the
cert CN) + a `claims` param — through a **stock** `rabbitmq:4.1-management`
image with only our mechanism plugin mounted.

Everything runs locally in Docker; nothing touches prod.

## Run

```shell
./certs/gen_certs.sh          # test CA + server cert + client cert (CN = fake GNodeId)
./plugin/build_ez.sh          # compile the .ez INSIDE rabbitmq:4.1-management (erlc ships in it)
docker compose up -d          # broker (TLS 5671, GRIDWORKS mechanism, http auth backend) + stub FIS
uv run --with pika client_test.py   # connect with cert + claims; expect success
docker compose logs stub-fis  # the witness: username = cert CN, claims = the payload, verbatim
```

## What passes

- stub FIS log shows a `/auth/user` POST with `username=<the client cert's
  CN>` and `claims=<the JSON sent in the SASL response>` — the design's
  claims channel, end to end.
- A connection WITHOUT a client cert fails at the TLS handshake
  (`fail_if_no_peer_cert = true`).
- `STUB_DELAY_S=2 docker compose up` still connects — start of the
  auth-callback timeout-budget measurement (design "Build-time artifacts").

## Files

- `plugin/rabbit_auth_mechanism_gridworks.erl` — the two-change fork of
  stock `rabbit_auth_mechanism_ssl` (which ignores the SASL response and
  passes `AuthProps = []`): parse nothing, pass `[{claims, Response}]`.
- `plugin/build_ez.sh` — in-container compile + `.ez` packing.
- `stub_fis.py` — stdlib-only HTTP server: logs every `/auth/*` body,
  answers `allow`.
- `client_test.py` — pika with a custom `TYPE = "GRIDWORKS"` credentials
  class (the shape the gwbase class will take).
