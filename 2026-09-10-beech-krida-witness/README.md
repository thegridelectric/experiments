# beech-krida-witness, 2026-09-10

Status: Draft · Pass 0 · Updated 2026-09-10

> What this is: the hardware witness for the House0 relay decommission
> (krida-retirement rung 3): a window scada on the real beech box, on
> the per-relay code, admin taking one zone on the second Krida board
> and making a heat call, the Caleffi zone box starting the
> distribution pump, flow and pump power watched for a few minutes,
> then the call released and beech handed back. Verdict in "Found".

## Why

Rung 3 moved every House0 relay onto a thin `i2c.relay.component.gt`
against the Krida board record and gave `relay.py` one I2C actuation
path, with the bus actor writing a PCF8575 as one port word. That is
proven only on the sim driver and the suite. The Krida panel is
active-low (a low bit energizes) and the two banks answer at 0x20 and
0x21, which is exactly the kind of fact a simulator agrees with by
construction. The design reaches Verified on this rung only when a real
Krida relay is driven from the admin panel and the pin reads back.

The only Krida panels are in the field. Beech's second board carries
nothing but the four zone thermostat relays, so it is the bank to
exercise in September: energizing a failsafe relay moves that zone's
heat-call source to the scada while the ops relay stays open, so the
zone sees no call for the seconds it is held.

| Krida marking | node | wiring | de-energized |
| --- | --- | --- | --- |
| 17 | zone1-down-failsafe-relay | DoubleThrow | wall thermostat |
| 18 | zone1-down-ops-relay | NormallyOpen | open (no call) |
| 19 | zone2-up-failsafe-relay | DoubleThrow | wall thermostat |
| 20 | zone2-up-ops-relay | NormallyOpen | open (no call) |

## Setup

**Code under test.** gridworks-scada `jm/spruce-unlimbo` at `1a7a41d1`
(House0 relays on per-relay components against the Krida board record;
one I2C actuation path), in a full HTTPS clone at
`~/gridworks-scada-unlimbo` on beech with its own venv
(`tools/mkenv.sh`, admin installed, no flo). The deployed service in
`~/gridworks-scada` (`main`, `0f623987`) is stopped for the window and
never touched.

**Layout pair.** The two files in `instances/`, derived by `derive_beech_layout.py`
from the scada House0 fixture pair (the one House0 layout in the
per-relay shape): beech's real hw1 identity, zone 1 renamed main → down,
zone 2 (up) cloned with relays 19/20, `ActuationAuthority=Standby` so
the window's local control never actuates on its own, and beech's
instruments for the heat call: the real eGauge (`eGauge6069.local`,
the deployed register map, `dist-pump-pwr` at 9010) in place of the
fixture's simulated meter, and the `dist-btu` pico BTU meter
(`pico_47352a`: `dist-flow`, `dist-swt`, `dist-rwt`) with the web server
on 8000 where beech's picos post. Everything else is the fixture's
(simulated tank modules, a hubitat that is not beech's); the pair
decodes through gwsproto (`sema_to_dc.load_layout`: 64 nodes, 15
relays, both expanders PCF8575, RelayEnergizedLevel 0) and is placed
on the box as
`~/.config/gridworks/scada-experiment/hardware-layout.json` +
`operational-params.json` by `beech_window.sh on`.

| file | type | sha256 (first 16) |
| --- | --- | --- |
| `instances/beech-window-gw.house0.layout-000.json` | `gw.house0.layout/000` | `349c4a53d5bce1fb` |
| `instances/beech-window-gw.house0.operational.params-000.json` | `gw.house0.operational.params/000` | `92c174ec509c2733` |

**Isolation.** `~/envs/dev.env` on the box: real beech identity, dev
broker creds only, upstream over the laptop's `ssh -R 1885` tunnel to
`gw-dev-rabbit` (nothing reaches the hw1 broker), events under the
`scada-experiment` paths root, admin link on the box's own mosquitto.
The window boots through `../2026-08-10-ads-declared-rate/window_boot.py`
with a 300 s bound and self-terminates.

**Summer posture.** The deployed beech runs `SCADA_SYSTEM_MODE=Standby`,
and the first board read `0xf2 0xdf` before the window: relays 5, 6, 8
and 14 energized (hp failsafe to scada, hp ops open, aquastat control
to scada so the oil boiler stays off, hp loop off). The window's ops
params carry `ActuationAuthority=Standby`, so its StandbyLocalControl
sets that same posture at boot (`initialize_actuators`: de-energize the
rest, energize those four). Nothing is replicated by hand.

**Protocol.**

1. `./beech_window.sh on`: stops `gwspaceheat` and its 15-minute
   restart timer, records both port words, boots the window scada
   (4 h safety bound; the experiment ends it). Boot cycles the
   vdc-relay once, as every deployed restart does.
2. `heat_call.py drive-<stamp>.log broker-<stamp>.jsonl` from the
   laptop, in the scada venv: waits 60 s of snapshots, then admin
   SwitchToScada on zone1-down-failsafe-relay (17) and CloseRelay on
   zone1-down-ops-relay (18), the heat call. The Caleffi box should
   start the distribution pump about 40 s later.
3. The hold: 180 s of snapshots every 10 s logging the dist flow and
   pump power rows and the two relay states; `./beech_window.sh status`
   for the port words (17 energized: 0x21 low byte `0x7f`; 17 and 18:
   `0x3f`).
4. Release: OpenRelay on 18, SwitchToWallThermostat on 17, admin
   release; 60 s more of snapshots while the standby control resumes.
5. `./beech_window.sh off`: port words after, the boot log and the
   scada's pending report events (unacked, no LTN on the dev broker)
   copied into this folder, the deployed service and timer restarted.
6. Afterwards: the report events are sema-fied into `instances/` and
   this README is put in order (Found, Timeline, the data manifest).

The bar: each commanded transition shows in the panel row, in the bus
actor's readback in the boot log, and in the port word read off the
bus; the pump starts under the call and stops after it; the deployed
scada comes back with both port words as they were before the window.

**Dev rung (2026-09-10 21:02–21:07 ET).** Before beech, the same driver
against the House0 sim fixture (`gw.house0.sim.layout.json`, orange1,
one zone) on the dev broker, scada from `jm/spruce-unlimbo` `1a7a41d1`
with the admin link on the dev broker and a 60 s hold:

```sh
cd gridworks-scada && export PYTHONPATH=$PWD/gw_spaceheat
SCADA_PATHS__HARDWARE_LAYOUT=$PWD/tests/config/gw.house0.sim.layout.json \
SCADA_PATHS__OPERATIONAL_PARAMS=$PWD/tests/config/gw.house0.sim.operational.params.json \
SCADA_ADMIN__ENABLED=true SCADA_ADMIN__HOST=localhost SCADA_ADMIN__PORT=1885 \
SCADA_ADMIN__USERNAME=smqPublic SCADA_ADMIN__PASSWORD=smqPublic SCADA_SECONDS_PER_REPORT=60 \
  timeout 600 gw_spaceheat/venv/bin/gws run > ../experiments/2026-09-10-beech-krida-witness/dev-scada.log 2>&1 &
cd ../experiments/2026-09-10-beech-krida-witness
HEAT_CALL_SCADA=d1.isone.ct.newhaven.orange1.scada HEAT_CALL_ZONE=zone1-main \
ADMIN_HOST=localhost ADMIN_PORT=1885 ADMIN_USER=smqPublic ADMIN_PASS=smqPublic HOLD_S=60 \
  ../../gridworks-scada/gw_spaceheat/venv/bin/python heat_call.py dev-drive.log dev-broker.jsonl
```

## Found

**Dev rung: PASS, all nine checks** (`dev-drive.log`). Both zone1-main
relay rows are in `scada.control.capabilities` for a House0 tree
(beside the eleven other relays, five-v-boss and hp-boss); each of the
four dispatches (SwitchToScada, CloseRelay, OpenRelay,
SwitchToWallThermostat) was acked within the second and the relay's
`single.machine.state` and the next snapshot showed the commanded
state; after admin release both relays read WallThermostat and
RelayOpen. This is the first time the admin path has been exercised
against a House0 layout.

**Beech: not yet run.**

## Timeline

(ET)

- 2026-09-10 21:02 dev rung: sim House0 scada booted on the dev broker.
- 21:04:19 driver: SwitchToScada acked, failsafe reads Scada by 21:04:23.
- 21:04:23 CloseRelay acked, ops relay RelayClosed by 21:04:27; 60 s hold.
- 21:05:27 OpenRelay acked; 21:05:31 SwitchToWallThermostat acked; admin released 21:05:35.
- 21:06:35 driver done, SUMMARY all PASS.

## Analysis notes

- The port word is read with `i2ctransfer -y 1 r2@0x21` (two bytes,
  P0-7 then P10-17). A PCF8575 read returns pin levels, so a bit reads
  low while the relay is energized; all `0xff` is every relay off.
- Nothing in the layout beyond the board and relays is beech's. Zone
  temperatures, tank readings and power in the window are simulated or
  absent and mean nothing.

## Folder contents & experimental method

All data here is GENERATED by the window (the boot log and the window's
event dir); nothing is pulled from the journal or the eventstore.

- `derive_beech_layout.py` — fixture pair → `instances/`, reproducible.
- `instances/` — the layout pair the window ran, and the scada's own
  report events from the window (copied by `off`).
- `beech_window.sh` — on / off / status from the laptop.
- `heat_call.py` — the admin driver: the zone taken, the call made and
  held, released; snapshots logged to `drive-<stamp>.log`, the
  dev-broker traffic to `broker-<stamp>.jsonl`.
- `boot-<stamp>.log` — the window scada's boot log (copied by `off`).
- `dev-scada.log`, `dev-drive.log`, `dev-broker.jsonl`,
  `dev-driver-stdout.txt` — the dev rung on the sim House0 fixture.
