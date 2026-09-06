# fis-staging-box, 2026-09-06

> What this is: stand-up-fis step 9 (OPS-422), the staging broker box for
> `hw1__2`: RabbitMQ with the FIS gate on and FIS beside it, on a box of
> its own, so the done-when battery can run for real (real TLS, real
> network, real boot order) and the prod gate cutover can rehearse. The
> box is **ephemeral** and this folder is its reproducer; the durable
> half, how FIS lives on any broker box, is `gridworks-infra/fis/`, and
> the broker files are `gridworks-infra/rmqbot/`. Verdict in "Found" once
> the battery (`../2026-09-05-fis-gate-battery/`) has run here.

## Why

Colocation is the spec (one FIS per broker box, localhost auth path), but
the box is not the prod broker: the battery kills connections by identity
and takes the management API down, and wiring the gate into prod is a
container recreate that wipes runtime users. Real identities (a bench pi,
beech's scada) join `hw1__2` here without disturbing `hw1__1`, against
the same registry.

## Setup

Hetzner Cloud, project `gridworks`, Helsinki (`hel1`), **ccx13** (2
dedicated vCPU / 8 GB / 80 GB; dedicated because the sizing driver is the
TLS reconnect storm), Ubuntu 24.04, server `hw1-2`, DNS
`hw1-2.electricity.works`. Two logins, one per service: `broker` (the
container, `~/rmq-docker`, the certs) and `fis`. Keys are the **rmqbot**
per-person keys (`rmqbot-{jessica,thomas,joe}`), this being the broker's
staging twin; root opens with `rmqbot-jessica`.

`rabbitmq.conf` here is the prod conf made TLS-only with the `ssl_options`
tightening (`fail_if_no_peer_cert = true`, prod's notch 3) and vhost
`hw1__2`; the gate itself stays the rmqbot fragment that
`compose.gate.yaml` mounts.

## Protocol (from a laptop checkout of the umbrella; one command per block)

Prerequisites: `hcloud` with the `gridworks` context and the rmqbot key
uploaded once (`hcloud ssh-key create --name rmqbot-jessica --public-key-from-file ~/.ssh/rmqbot-jessica.pub`),
`gridworks-infra/authority/ca.crt`, a gwbase checkout, 1Password: a fresh
default-user credential for this broker (never the prod one), the
mechanism `.ez` built for the pinned image
(`gridworks-infra/rmqbot/auth-mechanism/build.sh`).

**1. Server + IP + firewall.** Inbound: ssh, AMQPS, MQTTS, the TLS
management UI, ICMP. Plain management 15672 stays closed: FIS reaches it
on localhost.

    hcloud primary-ip create --type ipv4 --name hw1-2 --datacenter hel1-dc2 --auto-delete=false

    hcloud server create --name hw1-2 --type ccx13 --location hel1 --image ubuntu-24.04 --primary-ipv4 hw1-2 --ssh-key rmqbot-jessica

    hcloud firewall create --name hw1-2 && for p in 22 5671 8883 15671; do hcloud firewall add-rule hw1-2 --direction in --protocol tcp --port $p --source-ips 0.0.0.0/0 --source-ips ::/0; done && hcloud firewall add-rule hw1-2 --direction in --protocol icmp --source-ips 0.0.0.0/0 --source-ips ::/0 && hcloud firewall apply-to-resource hw1-2 --type server --server hw1-2

**2. Base OS** (as root). The `fis` login and its sudoers come from
`gridworks-infra/fis/README.md` "Add FIS to a broker box"; here the
`broker` login and sshd:

    apt-get update && apt-get install -y docker.io docker-compose-v2 git

    adduser --disabled-password --gecos '' broker && usermod -aG docker broker && install -d -m 700 -o broker -g broker /home/broker/.ssh

    printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' > /etc/ssh/sshd_config.d/50-gridworks.conf && systemctl reload ssh

Then `authorized_keys` for `broker` and `fis`: the rmqbot per-person
public keys, one per line.

**3. Broker cert** (on certbot, per-person ssh; a row in
`gridworks-infra/authority/cert-inventory.md`). One keypair serves AMQPS,
MQTTS and the management UI, as on prod:

    gwcert key add --common-name hw1-2.electricity.works --dns hw1-2.electricity.works --valid-days 730 hw1-2

Place `ca.crt`, the cert as `rmq-cert.crt` and the key as `rmq-key.pem` in
`/home/broker/rmq-certs-2026/`; the key mode 600 owned by uid 999
(`chown 999:999 rmq-key.pem`), or the broker boot-loops with "keyfile
invalid".

**4. Broker files** (from the laptop). The box carries both rmqbot
directories (the overlay mounts the `.ez` from `../auth-mechanism`), this
folder's conf over the prod one, and definitions rendered for `hw1__2`:

    rsync -a --exclude .env gridworks-infra/rmqbot/rmq-docker/ broker@hw1-2.electricity.works:rmq-docker/

    rsync -a gridworks-infra/rmqbot/auth-mechanism/ broker@hw1-2.electricity.works:auth-mechanism/

    scp experiments/2026-09-06-fis-staging-box/rabbitmq.conf broker@hw1-2.electricity.works:rmq-docker/config/rabbitmq.conf

    (cd gridworks-base && uv run python for_docker/gen_definitions.py --vhost hw1__2) | ssh broker@hw1-2.electricity.works 'cat > rmq-docker/config/rabbit_definitions.json'

Then `~/rmq-docker/.env` (mode 600) as `broker`:
`RMQ1_CERTS=/home/broker/rmq-certs-2026`, `RMQ1_USER`, `RMQ1_PASSWORD`.

**5. Broker up, gate OFF, default user** (as `broker`). The gate comes on
only after FIS answers; until then the box is prod at notch 3:

    cd ~/rmq-docker && docker compose up -d

    docker exec rmq1 bash -c 'rabbitmqctl add_user "$RMQ_DEFAULT_USER" "$RMQ_DEFAULT_PASS" && rabbitmqctl set_user_tags "$RMQ_DEFAULT_USER" administrator && rabbitmqctl set_permissions -p hw1__2 "$RMQ_DEFAULT_USER" ".*" ".*" ".*"'

**6. FIS.** `gridworks-infra/fis/README.md` "Add FIS to a broker box",
with `FIS_UNIVERSE=hw1` and this box's `RMQ1_*` credential as the
management credential. Ends with `/ping` answering on the box.

**7. Gate ON** (as `broker`). A container recreate: re-mint the default
user afterwards (step 5's second block).

    cd ~/rmq-docker && docker compose -f compose.yaml -f compose.gate.yaml up -d

    docker exec rmq1 rabbitmq-plugins list | grep -E 'auth_backend_http|gridworks'

    docker exec rmq1 rabbitmqctl environment | grep -A3 auth_backends

**8. DNS** (Jessica): Route 53 `hw1-2.electricity.works` A → the primary
IP. Then from the laptop:

    openssl s_client -connect hw1-2.electricity.works:5671 -CAfile gridworks-infra/authority/ca.crt </dev/null | grep Verify

**9. Principals, then the battery.** The battery identities' rows (and the
four platform services) minted here with the same ids as records; then the
staging run of `../2026-09-05-fis-gate-battery/`, which needs its remote
rung (broker host from the environment, FIS and the management-API-down
leg over ssh, certs cut on certbot against the real CA).

## Drop the box

    hcloud server delete hw1-2

The primary IP and firewall survive for the next build (delete them too if
staging is not coming back). Retire the cert-inventory row and the DNS
record.

## Found

Battery not yet run here.

## Timeline

- 2026-09-06 08:39 ET: rmqbot key uploaded to Hetzner; primary IP
  `204.168.249.110`, firewall `hw1-2` (22, 5671, 8883, 15671, ICMP),
  server `hw1-2` (ccx13, hel1) created and firewall applied.
- 08:41: base OS done (docker, `broker` + `fis` logins with the rmqbot
  per-person keys, sshd key-only, `/etc/sudoers.d/fis`, `/mnt/pgdata/fis`,
  CA in the trust store).
- 08:42: broker files rsynced, this folder's conf over the prod one,
  definitions rendered for `hw1__2`; broker `.env` with a fresh
  `smqPublic` credential (recorded nowhere but the box's two `.env`
  files: copy it into 1Password from there).
- 08:42: broker cert minted on certbot (`hw1-2`, expires 2028-09-05,
  which is later than the summer policy; acceptable for an ephemeral
  box), placed on the box, certbot copy removed. Route 53 A record
  `hw1-2.electricity.works` created.
- 08:43: broker up, gate OFF, `hw1__2` the only vhost, `smqPublic`
  minted as administrator. TLS verified from the laptop against the
  GridWorks CA (`Verify return code: 0`).
- 08:44: `fis` login: uv installed, `fis-postgres` up on loopback
  :5437, `.env` staged as `~/fis.env` (moves into the checkout once the
  FIS branch is pushed); the registry façade answers from the box.
- 08:49: `jm/stand-up-fis` pushed (`68966d2`); FIS cloned on that branch
  (a flagged deviation from `main`, deliberate: prove it before the
  merge), synced, migrated, `fis-api.service` enabled; `/ping` ok; the
  mirror filled with the 25 `hw1` nodes from the registry.
- 08:51: gate ON (compose overlay, a recreate; `smqPublic` re-minted):
  both plugins enabled, backends `[internal, http]`, mechanisms
  `[GRIDWORKS, PLAIN, AMQPLAIN]`. `fis` added to `systemd-journal`.
- 08:50: FIRST FINDING. A bogus-user login through the management API
  returned 401 but FIS saw nothing; the broker log said
  `rabbit_auth_backend_http ... econnrefused` to 8080: inside the bridged
  container `localhost` is the container. Fixed by `network_mode: host`
  in `compose.gate.yaml` (mirrored into gridworks-infra); after the
  recreate, the same probe reached FIS (`POST /auth/user 200`, a deny).
- 08:55: SECOND FINDING. The deny left no verdict line in the journal:
  FIS logs verdicts at INFO and nothing configured logging under
  systemd. `fis api` now calls `logging.basicConfig` (FIS repo, pending
  push). No `auth_events` row either, by design: a login with no claims
  fails at parsing, before there is an instance or run to record.
- 16:48–17:05: step 9 done. The battery identities minted here (three
  GNode rows with the registry's ids, 100 service rows), their certs cut
  on certbot, and `../2026-09-05-fis-gate-battery/` run on its remote
  rung against this box: 27/27, storm 100/100 (max 3.0 s). The green
  run is that folder's `battery-2026-09-06-hw1-2.log`. The box is left
  as found: FIS under systemd, gate ON. The four platform-service
  principals are not minted here yet.
- 17:30: box dropped: server, primary IP and firewall deleted on
  Hetzner, the Route 53 A record removed, the two cert-inventory rows
  (broker cert, battery client certs) retired. The battery's client
  certs in the laptop checkout are now certs for a host that no longer
  exists; `setup-remote.sh` re-cuts them against a rebuilt box.
