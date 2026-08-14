# SASL mechanism — claims through a stock 4.1 broker to a stub FIS

The re-runnable witness for the mTLS+FIS design's claims channel (OPS-420,
OPS-496): a client cert plus a `fis.connect.claims`-shaped payload in the
SASL response arrive at the auth backend's `user_path` as `username` (from
the cert CN) and a `claims` param — through a **stock**
`rabbitmq:4.1.8-management` image with only the GridWorks mechanism plugin
mounted.

Both halves under test are the shipped ones, not imitations of them. The
plugin lives in `gridworks-infra/rmqbot/auth-mechanism/` (rmqbot owns the
artifact) and this harness mounts the **built `.ez` from there**; the client
uses **gwbase's own credentials class** and the `fis.connect.claims` word
from its vendored snapshot. Build the plugin before bringing the harness up.

Everything runs locally in Docker; nothing touches prod.

## Run

```shell
(cd ../../gridworks-infra/rmqbot/auth-mechanism && ./build.sh)   # the .ez this harness mounts
./certs/gen_certs.sh                 # test CA + server cert + client cert (CN = fake GNodeId)
docker compose up -d                 # broker (TLS 5671, GRIDWORKS mechanism, http auth backend) + stub FIS
docker compose exec broker rabbitmqctl add_vhost d1__1          # the run being joined
uv run --with pika --with ../../gridworks-base actor_test.py     # a real ActorBase actor, settings-driven
uv run --with pika --with ../../gridworks-base client_test.py    # hand-built claims (arbitrary-payload leg)
docker compose logs stub-fis         # the witness: username = cert CN, claims = the payload, verbatim
```

`actor_test.py` is the end-state witness: the actor builds its claims from
its own alias/instance/run and the settings `tls` block switches it to
cert-plus-claims connect — nothing assembled by hand. `client_test.py`
stays as the arbitrary-payload leg (useful for driving FIS with claims an
honest gwbase actor would never send).

The vhost is a real run name rather than `/` so that `/auth/vhost` carries
`d1__1` — the value FIS cross-checks against the `Run` in the claims, since
its single-writer lease is scoped to (identity, run). It is a dev (`d`)
universe because the broker is on localhost: gwbase enforces the universe
ladder's dev rung (localhost ⟺ d-kind universe) at settings construction,
so an ActorBase leg claiming `hw1__1` here would refuse to boot.

The broker image is pinned to the same patch as prod, which is also the image
the plugin is compiled in — a beam built on another OTP major will not load,
and the failure looks like a healthy broker that authenticates nobody.

## What passes

- stub FIS log shows a `/auth/user` POST with `username=<the client cert's
  CN>` and `claims=<the JSON sent in the SASL response>` — the design's
  claims channel, end to end.
- `docker exec ... rabbitmq-plugins list | grep gridworks` shows `[E*]` —
  the mounted `.ez` was accepted and the mechanism registered.
- A connection WITHOUT a client cert fails at the TLS handshake
  (`fail_if_no_peer_cert = true`) — witnessed as
  `TLSV13_ALERT_CERTIFICATE_REQUIRED`, i.e. refused before any auth
  exchange, so no claims can substitute for having a certificate.
- `STUB_DELAY_S=2 docker compose up` still connects — start of the
  auth-callback timeout-budget measurement. A 10s delay fails, consistent
  with the broker's default 10s `handshake_timeout` bounding the whole auth
  sequence.

## Files

- `stub_fis.py` — stdlib-only HTTP server: logs every `/auth/*` body,
  answers `allow`. `STUB_DELAY_S` stalls each answer, for budget probing.
- `client_test.py` — pika with a custom `TYPE = "GRIDWORKS"` credentials
  class (the shape the gwbase class will take).
- `rabbitmq.conf` / `enabled_plugins` — TLS-only, client certs required,
  GRIDWORKS as the only mechanism, all auth delegated to the stub over HTTP.
