# prod-broker-outage-drill-2, 2026-11-25

Status: Accepted · Pass 0 · Updated 2026-11-25

> What this is: the second planned stop of the prod broker, run the
> same morning the fleet took gridworks-proactor `v4.1.13+jm4` (one
> jittered reconnect schedule capped at 30 s, keepalive 30 s; OPS-304),
> to see how the MQTT fleet returns compared with the 2026-10-11 drill
> (`../2026-10-11-prod-broker-outage-drill/`).

## Why

The October drill found the MQTT clients returning 46 to 49 s after a
broker that was already accepting, all six LTNs within 42 ms of each
other: paho's default schedule, 1 s doubling to a 120 s cap with no
jitter, every client in phase because all lost the broker in the same
second. jm4 replaces that with a proactor-owned schedule, full jitter in
[0, step], the step doubling from 1 s to a 30 s cap. The prediction: after
an outage longer than about half a minute every client is at the cap, so
on the broker's return they arrive spread across the next 30 s.

## Setup

- All six houses on scada `1393c09b` (main), LTN and pis, rolled between
  09:46 and 09:55 ET the same morning; every MQTT client on the broker
  runs jm4.
- Stop and start on `hw1-1` over ssh as `ubuntu`: `cd ~/rmq-docker &&
  sudo docker compose stop`, then `start`, from `runbook.sh` (the October
  runbook; `START`/`END` set to this window). FIS kept running. Nothing
  else touched.
- Outage held to 150 s so the alerter's prober (BrokerUnreachable at
  3 to 4 minutes) would not raise and page. gwalert's silence threshold
  is 10 minutes.
- Clients on the broker before the stop: 13 MQTT (six scadas, six LTNs,
  the prober's check) and 11 AMQP. The same counts after.
- Clocks: broker lines are UTC; box journal lines are box-local ET. The
  two agreed to within a few hundred milliseconds on this run (fir's
  `mqtt_connected` at 10:12:46.814 ET, its accept at 15:12:46.80Z).

## Found

1. **PASS: the MQTT fleet returned spread across 24 s, every client
   inside the 30 s cap.** The MQTT TLS listener started at 15:12:43.68Z.
   The twelve fleet clients were accepted from +3.1 s (fir's scada) to
   +27.2 s (spruce's scada); the largest gap between two accepts was
   6.3 s and no two arrived within the same 100 ms. In October the same
   twelve arrived at +46 to +49 s, six of them within 42 ms.
2. **Every link was active again within 28 s of the listener.** Scadas
   and LTNs that reconnected before their peer sat in `awaiting_peer`
   until the peer arrived (beech's scada 15 s, elm's 14 s), as the link
   state machine specifies. Maple's and oak's scadas each took one
   `response_timeout` flap at 10:13:00 ET, five seconds after their
   first report, and were active again within 150 ms: the known 5 s ack
   timeout meeting an LTN still restoring its session.
3. **AMQP clients were back in a single second**, ten of the eleven
   between 15:12:58.5Z and 15:12:59.7Z (+15 to +16 s), the eleventh is
   the prober's check at 15:13:14Z. In October: 0.3 to 30 s.
4. **No alert.** The outage ended 151 s after the stop, under the
   prober's threshold; the prober's MQTT check reconnected at 15:13:15Z
   and 15:14:16Z and hung up as designed.

Return of each client after the MQTT listener started (15:12:43.68Z),
from the broker's accept lines matched to the boxes' `mqtt_connected`:

| client | accepted at (Z) | after listener | active (box ET) |
| --- | --- | --- | --- |
| fir scada | 15:12:46.80 | 3.1 s | 10:12:53.3 |
| elm scada | 15:12:50.67 | 7.0 s | 10:13:05.0 |
| beech scada | 15:12:52.19 | 8.5 s | 10:13:07.4 |
| fir LTN | 15:12:53.00 | 9.3 s | 10:12:53.4 |
| maple scada | 15:12:55.09 | 11.4 s | 10:12:57.2 |
| oak scada | 15:12:55.13 | 11.4 s | 10:12:58.7 |
| spruce LTN | 15:12:55.64 | 12.0 s | 10:13:11.0 |
| maple LTN | 15:12:56.95 | 13.3 s | 10:12:57.3 |
| oak LTN | 15:12:58.43 | 14.7 s | 10:12:58.8 |
| elm LTN | 15:13:04.74 | 21.1 s | 10:13:05.1 |
| beech LTN | 15:13:07.13 | 23.5 s | 10:13:07.5 |
| spruce scada | 15:13:10.88 | 27.2 s | 10:13:11.1 |

## Timeline (UTC)

- 15:10:01 census.
- 15:10:03 `docker compose stop`; MQTT and AMQP listeners stopped
  15:10:04.5; every box logged `mqtt_disconnected` at 10:10:04.6 ET.
- 15:12:40 `docker compose start`; listeners up 15:12:43.7, startup
  complete 15:12:43.7.
- 15:12:46.8 to 15:13:10.9 the twelve MQTT fleet clients accepted.
- 15:12:58.5 to 15:12:59.7 ten AMQP clients accepted.
- 15:13:11 the last link (spruce scada) active.
- 15:14:44 evidence collected.

## Analysis notes

- The spread is the jitter doing its work: with every client at the
  30 s cap when the broker returned, each waited a fresh uniform draw in
  [0, 30] from the end of its last refused attempt, so arrivals fall
  anywhere in the first ~30 s after the listener is up. Twelve draws
  gave a 24 s span; two hundred would fill the 30 s at about seven
  logins a second.
- The scadas reconnected 3 to 27 s after the listener, the LTNs 9 to
  24 s. Both populations run the same code; the difference is draw
  luck.
- A house whose scada reconnects before its LTN sits in `awaiting_peer`
  until the LTN's first message, so the house-level recovery time is
  the later of the two plus the LTN's session restore, 28 s worst case
  here.
- Not measured: the half-open blackhole case (the 2026-02-12 incident
  shape). This drill is the outage case; the fault-injection experiment
  for the blackhole is still the open bar for Verified on the
  reconnect schedule (scada executor `scada-ltn-link-state.md`
  "Broker-access liveness").

## Folder contents & experimental method

- `runbook.sh`: the October runbook with this run's window; `census`,
  `stop`, `start`, `collect`.
- `evidence/drill-steps.log`: the stop/start timestamps as run.
- `evidence/mqtt-connections-{before,after}.tsv`,
  `evidence/amqp-connections-{before,after}.tsv`: `rabbitmqctl`
  connection lists.
- `evidence/broker-log-reduced.txt`: the broker log for the window
  reduced to listener, startup, accept and auth lines, each public IP
  replaced by a stable token. The raw log held public IPs and was not
  kept.
- `evidence/journals-scada.txt`, `evidence/journals-ltn.txt`: each
  box's unit journal for the window, link transitions only. scada2
  units logged nothing: their only link is the pi's local broker.
- `views.py`: copied from October; not run here, the table above was
  built by hand from the two evidence files.
- `arrivals_chart.py`, `arrivals-before-after.png`: one dot per fleet
  client accepted, seconds after the MQTT listener came up, the October
  drill above this one (`uv run --with matplotlib python
  arrivals_chart.py` regenerates it).
