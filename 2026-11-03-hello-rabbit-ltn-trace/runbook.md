# Runbook, as run (ET, 2026-11-03)

Laptop, `d1` universe, `gw-dev-rabbit` already up (AMQP 5672, MQTT 1885,
vhost `d1__1`). Branches: `gridworks-ltn` on `jm/hello-world` (the port,
uncommitted beyond 535648a), `gridworks-scada` on `main`.

## Placement

- 22:33 capture: `cd experiments && uv run python capture_broker.py 2026-11-03-hello-rabbit-ltn-trace/captures > .../logs/capture.log` → `capturing vhost d1__1`.
- LTN identity `g.node.gt.json` (this folder): alias `d1.isone.me.versant.keene.spruce`, the Nolan pair's LTN. `gridworks-ltn/.env` from `template.env`: that alias, `GWLTN_G_NODE_PATH` to the identity, `GWLTN_WEATHER_SOURCE=Sim`.
- 22:34 first start of both FAILED the same way: the laptop's placed Nolan pair (`~/.config/gridworks/{scada,ltn}/`) lagged the scada repo's fixture (`NolanLayout` now requires `Hydronic.Circulators`, `WaterStore.GallonsPerTank`, `TempSensorsPerTank`).
- `experiments/put_layout.sh dev circulators-store-tanks` placed the scada layout, then its params prompt read the next line of its own `PLACES` here-string instead of the terminal, refused, and skipped the `ltn/` folder. Placed the rest by hand the way the script does (dated `*-pre-circulators-store-tanks.json` copies beside each file); `put_layout.sh dev check` then all identical. Script defect noted for OPS-614.

## Run

- 22:35:03 LTN: `cd gridworks-ltn && uv run gwltn rabbit > .../logs/ltn.log 2>&1`
- 22:35:06 scada: `cd gridworks-scada && SCADA_GRIDWORKS_MQTT__PORT=1885 gw_spaceheat/venv/bin/gws run --message-summary > .../logs/scada.log 2>&1`
- 22:35:06.926 the scada's `gridworks_mqtt` link went `awaiting_peer -- message_from_peer --> active` on the LTN's ack of the scada's first ping; `PeerActiveEvent` and `layout.lite` followed; the LTN asked `send.layout` and got a second `layout.lite`. The scada reuploaded about 750 persisted events from earlier laptop runs, each acked inside 10 ms.
- 22:36:03 and 22:37:04 the LTN's 60 s pings; 22:36:00 and 22:37:00 the scada's `report.event` (ack-required), each acked.
- 22:37:29 `kill -TERM` the LTN (pid 44210). VOID LEG: `pmset -g log` shows the laptop entered Maintenance Sleep at 22:37:32 and woke 22:53:02; the scada log and the capture have nothing in between. On wake the scada's watchdog (pico-cycler pat 1080 s ago, 630 allowed) stopped the scada cleanly (exit 0, `gridworks.event.shutdown` to the LTN at 22:53:07). Nothing of the scada without its peer was witnessed.

## Run 2 (the away-and-back legs, laptop held awake)

- `caffeinate -i ./run_legs.sh` from this folder, the capture still recording into the same file. Timeline in `logs/clock.txt` (`run2 ...` lines), logs `logs/ltn-run2.log`, `logs/scada-run2.log`, `logs/ltn-run2b.log`.
- Run 2 (`caffeinate -i`, 22:54 to 23:57) was VOID too: the pmset log shows Maintenance Sleep from 22:56:07 with dark wakes only, until a user wake at 00:01:04. `caffeinate -i` asserts only `PreventUserIdleSystemSleep`, which does not hold a machine already cycling through SleepService dark wakes.

## Run 3 (the legs, witnessed; `RUN=run3 caffeinate -dims ./run_legs.sh`, 2026-11-04)

- 00:02:25 LTN start; 00:02:28 scada start. 00:02:29.814 scada ping (ack-required) to the LTN; 00:02:29.816 LTN ack; 00:02:29.819 `gridworks_mqtt: awaiting_peer -- message_from_peer --> active`; peer-active event, `layout.lite`; 00:02:31 the LTN's `send.layout`, a third `layout.lite`.
- 00:03:00 and 00:04:00 scada `report.event` (ack-required), acked inside 5 ms. 00:03:26 the LTN's 60 s ping (no ack asked, none given).
- 00:04:03 LTN `kill -TERM`, exited 143. The LTN said nothing on the broker as it left.
- 00:05:00.020 scada `report.event` 4e777b45, ack-required; no ack. 00:05:05.019 `gridworks_mqtt: active -- response_timeout --> awaiting_peer`; 00:05:05.024 the scada sends ONE `gridworks.ping` (ack-required) to the LTN topic and nothing else. The `gridworks.event.comm.response.timeout` it generated went to the persister, not the broker.
- 00:05:43 LTN start again. 00:05:49.448 the LTN's `send.layout` is the first message the scada hears; 00:05:49.449 `awaiting_peer -- message_from_peer --> active`; 00:05:49.454 the reupload: the unacked `report.event` 4e777b45 again, the `response.timeout` event (PeerName `gridworks_mqtt`, created 00:05:05), the new `peer.active` event; all three acked inside 5 ms; two `layout.lite` (one for the activation, one for `send.layout`).
- 00:06:00, 00:07:00 report events acked; 00:06:44 the LTN's ping. 00:07:18 LTN SIGTERM, scada SIGINT (clean exit 0).
