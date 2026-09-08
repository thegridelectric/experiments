# spruce-admin-panel, 2026-09-08

Status: Verified · Pass 0 · Updated 2026-09-08 · Reviewed 2026-09-08@ea3365b5

> What this is: the real admin TUI (`gwa watch spruce`) against a window
> scada on the real spruce gw108 (krida-retirement rung 1, first real
> hardware): does the panel render the Nolan command tree, does Reboot
> picos cycle the vdc-relay and bring the real picos back, and do a
> secondary-pump toggle and an iso-valve toggle from the panel show in
> `secondary-flow`. Verdict in "Found".

## Why

Rung 1 of krida-retirement was witnessed only on the dev-broker sim
(`../2026-09-07-admin-reboots-picos/`): sim relays, sim picos. Admin is
how a human runs a house during bring-up and three Nolan houses go in
this fall, so the panel has to be shown driving real relays through a
real expander and reading state back from real picos before the design
calls rung 1 verified. Spruce is the one Nolan house running, and the
window had to happen before the house was unpowered for hardware work.

## Setup

**Code under test.** gridworks-scada `jm/spruce-unlimbo` at `ea3365b5`
(the window ran the pre-squash tree `c8555abe`, which `ea3365b5` equals
plus one log line; rung 1 plus the 09-08 dev-broker fixes: cycler and command-node rows
follow `machine.states` live, ack/nack toasts). Pulled into the box's
`~/gridworks-scada-unlimbo` checkout; the deployed service in
`~/gridworks-scada` (`actual-spruce`, `30fc7f59`) was stopped for the
window and never touched.

**Artifacts consumed** (the spruce pair from the 09-06 sweep, in
`~/.config/gridworks/scada-experiment/` on the box; both decode on
`ea3365b5`, checked on the laptop with `sema_to_dc.load_layout` before
the window):

| file | type | sha256 (first 16) | mtime |
| --- | --- | --- | --- |
| `hardware-layout.json` | `gw.nolan.layout/000` | `262d9f7a581ae8f9` | 2026-09-06 09:01:45 |
| `operational-params.json` | `gw.nolan.operational.params/000` | `454b2c02ddee5924` | 2026-09-06 09:01:45 |

**Isolation.** As the 09-06 sweep: the window scada boots through
`~/experiments/2026-08-10-ads-declared-rate/window_boot.py` from
`~/envs/dev.env` (real spruce identity, dev-broker creds only, upstream
through the laptop's `ssh -R 1885` tunnel, paths root
`scada-experiment`, so its events and logs never share a directory with
the deployed scada's). The admin link rides the box's own mosquitto
(`localhost:1883`, the local link's user). `gwa` ran on the laptop,
reaching that mosquitto over tailscale (`100.69.205.1:1883`), registered
as scada `spruce` in `~/.config/gridworks/admin/admin-config.json`.

**Roles.** JM drove the panel. The session ran the box: stopped and
restarted the services, booted the window scada, read its log between
clicks, and restored.

**Plant state at the start** (the summer hack's on-peak OFF posture):
iso valve open, secondary pump off, heat-pump call open. The hack was
stopped for the window and exits to failsafe. Cooling stakes: none.

**Hazard carried from `2026-08-23-spruce-relay-stress/`:** energizing
the iso relay with no other 0x21 coil energized resets that expander
about one toggle in three. So the pump was toggled with the valve left
open, and the valve only toggled with the pump on.

**Flow readout.** `secondary-flow` (GpmTimes100) from the secondary BTU
pico. The scada's own `report.event` files are the record (the pico's
cadence, about a reading per second while flow changes); a box-side
snapshot watcher (`flow_watch.py`, 30 s cadence) ran alongside and is
the only record after the last report.

## Protocol

1. Laptop: push `jm/spruce-unlimbo`; box: pull `~/gridworks-scada-unlimbo`.
2. Laptop: `ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 spruce`
   (dev rabbit up on 1885).
3. Box: `sudo systemctl stop gwspaceheat-restart.timer gwspaceheat spruce-summer-hack`.
4. Box: boot the window scada for 15 min with cycler state logging:

       mkdir -p /tmp/spruce-admin-panel
       cd ~/gridworks-scada-unlimbo/gw_spaceheat && SCADA_PICO_CYCLER_STATE_LOGGING=true setsid nohup timeout 960 venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py 900 ~/envs/dev.env > /tmp/spruce-admin-panel/boot.log 2>&1 < /dev/null &

   The boot cycle (`Startup`) cycles the vdc-relay at once; the real
   picos reboot behind it. That is power-cycle observation one.
5. Box: the snapshot watcher (this run: `flow_watch.py` copied to
   `/tmp/spruce-admin-panel/` and launched there; next time it runs from
   the `~/experiments` clone as the convention requires):

       cd /tmp/spruce-admin-panel && setsid nohup timeout 900 ~/gridworks-scada-unlimbo/gw_spaceheat/venv/bin/python flow_watch.py > flow.log 2>&1 < /dev/null &

6. Laptop: `gridworks-scada/gw_spaceheat/venv/bin/gwa watch spruce`.
   Bar: all twenty relays, the pico-cycler and hp-boss rows, and the
   DAC render; rows leave `?` as state reports arrive.
7. **vdc power cycle, commanded.** Reboot picos on the cycler row. Bar:
   the row walks RelayOpening, PicosRebooting, PicosLive; the vdc-relay
   row opens and closes under it; the picos re-POST.
8. **Secondary pump.** Iso valve already open. Pump on from its row;
   bar: `secondary-flow` rises from 0. Pump off; bar: flow returns to 0.
9. **Iso valve** (pump on first, then valve): close, bar: flow falls;
   open, bar: flow returns. Any 0x21 reset shows in the scada log as
   `expander 0x21 re-initialized`.
10. Release admin and quit the TUI; the window scada times out on its
    own, or `pkill -f "[w]indow_boot.py"` (the bracket keeps pkill from
    matching the ssh command line that carries it).
11. Restore: `ls ~/.local/share/gridworks/scada/event/` (the deployed
    dir) holds nothing window-born, then
    `sudo systemctl start spruce-summer-hack gwspaceheat gwspaceheat-restart.timer`.
    Copy `/tmp/spruce-admin-panel/` here and remove it; copy the window
    paths root's pending events (`~/.local/share/gridworks/
    scada-experiment/event/`) into `instances/` and clear that dir.

## Found

PASS on every bar, one window of nine minutes (10:22 to 10:31 ET).
Times below are from the scada's `report.event` instances
(`extract_window.py` prints them) unless a log is named.

- **The panel renders and drives a real Nolan scada.** `gwa watch spruce`
  linked at 10:23:24 and every command it sent arrived at the actor the
  row names: two Reboot picos, four relay and valve events, three DAC
  levels, and the release at 10:30:07.
- **vdc power cycle, three times** (boot cycle plus two commanded, FSM
  reports `8de921dc`, `dc5deb34`, `5bd77f7b`): RelayOpening, RelayOpen,
  5 s, RelayClosing, PicosRebooting, and PicosLive 7 to 9 s after the
  close (10:22:20, 10:23:48, 10:25:37), confirmed by the BTU picos
  re-POSTing. Real picos come back far inside the cycler's 60 s reboot
  wait; each wait then expires as a stale-cycle message and is ignored
  (boot log, the guard from `e0029d3d` doing its job).
- **Secondary pump against flow.** Pump on at 10:24:16: 4.86 gpm at
  10:24:17, 7.52 at 10:24:19, settling at 7.40. Pump off at 10:26:50:
  1.58 at 10:26:52, 0 at 10:26:54. Pump on again at 10:28:03: 7.32 at
  10:28:08.
- **DAC against flow.** 5.0 V at 10:25:36 with the pump on: 7.38 to
  3.99 to 3.75 gpm by 10:25:39. 7.5 V at 10:27:20 (pump off, no flow
  effect); the 10:28 pump-on at 7.5 V gave 7.32 gpm.
- **Iso valve against flow, pump running.** CloseValve at 10:28:43:
  2.73 at 10:28:44, 0.74 at 10:28:45, 0 at 10:28:46. The valve shuts
  in about three seconds. OpenValve at 10:29:37: the next report ends at
  10:29:59 with flow still 0; the snapshot watcher (`flow.log`) has 0 at
  10:30:00 and 7.31 gpm at 10:30:30, so the reopen takes between 23 and
  53 s.
- **One 0x21 expander reset**, boot log `expander 0x21 re-initialized`
  at 10:29:04, twenty seconds after CloseValve with the pump coil
  already energized; the report shows both 0x21 relays re-reporting
  their states at that instant. No output was lost: the valve reopened
  on command and the pump stayed on. The relay-stress finding stands,
  and the pump-first ordering did not prevent this one.
- **Known, not a bar:** the tank picos (`buffer`, `tank1`) POST params
  after every reboot and the scada rejects them, missing
  `PicoBoardVariant` and `MicropythonVersion` (`tank.module.params/200`;
  the six `gridworks.event.problem` instances here). Their readings
  still arrive (first buffer temps at 10:22:23, boot log). The firmware
  side is gridworks-pico PR #15, open, changes requested.
- **Interior command nodes do not handle their relays' acks** (boot
  log 10:22:33): on the auto path at boot, LocalControl told hp-boss
  TurnOff, the relay answered with `gw.dispatch.ack`, and hp-boss logged
  it as an unexpected message. Filed under Open in the krida-retirement
  spoke.
- **The window paths root held 165 pending events** from every window
  since 08-11, none of them a risk (dev-broker creds only). Today's
  sixteen are in `instances/` (twelve files; same-second mqtt
  connect/subscribed pairs collided on the name); the older 149 were
  cleared and not kept, being copies of events that reached the dev
  broker in their own windows.

## Timeline

- 10:21:59 deployed scada, its timer and the summer hack stopped.
- 10:22:03 window scada up (`ea3365b5`); 10:22:06 boot vdc cycle,
  PicosLive 10:22:20; 10:22:17 tank params POSTs rejected; 10:22:23
  buffer temps arrive; 10:22:33 hp-boss logs the relay's ack as
  unexpected.
- 10:23:24 admin link active. 10:23:36 Reboot picos, PicosLive 10:23:48.
- 10:24:16 pump on; 10:24:19 flow 7.52 gpm.
- 10:25:23 Reboot picos, PicosLive 10:25:37. 10:25:36 DAC 5.0 V;
  10:25:39 flow 3.75.
- 10:26:50 pump off; 10:26:54 flow 0. 10:27:20 DAC 7.5 V.
- 10:28:03 pump on; 10:28:08 flow 7.32. 10:28:43 CloseValve; 10:28:46
  flow 0. 10:29:04 expander 0x21 re-initialized.
- 10:29:37 OpenValve; 10:30:07 admin released; 10:30:30 flow 7.31
  (`flow.log`).
- 10:30:50 window scada and watcher killed; 10:30:58 deployed services
  restarted, summer hack back to HP OFF posture at 10:30:59 (iso open,
  call open, pump off); window events archived and cleared.

## Analysis notes

- The scada log names the target only for GPIO relays (vdc-relay logs
  its pin moves); an expander relay dispatch shows as `AdminDispatch
  event is CloseRelay` with no node. The report's `StateList` is the
  evidence for those. Worth a log line naming the node.
- `report.event` readings are the pico's own cadence, about one per
  second while flow changes and sparse when steady, so "flow at
  10:24:17" is a measurement; the `flow.log` times are 30 s snapshot
  bounds.
- `flow.log`'s "states:" column prints enum type names, not values
  (watcher bug, see `flow_watch.py`); read relay state from the reports.
- Whether a commanded cycle's FSM `TriggerId` equals the admin
  dispatch's id was not checked here (the boot log does not print the
  dispatch id); `../2026-09-07-admin-reboots-picos/` verified it on the
  sim.

## Folder contents & experimental method

All data was GENERATED by the window; nothing here is re-pullable from
the journal or the eventstore, because the window scada spoke only to
the dev broker and the deployed scada was stopped. A re-run is a new
window (Protocol 1 to 11), producing a new dataset.

- `README.md` — this file.
- `instances/` — the window scada's own persisted events for the
  window, copied from its paths root at restore and named under the
  on-disk grammar (`<HHMMSS>[-<node>]-<type.name>-<version>.json`):
  two `report.event/004` (the evidence for Found), six
  `gridworks.event.problem/001` (the tank params rejections), the
  startup, connect, subscribed and peer-active events.
- `extract_window.py` — decodes the two report events through gwsproto
  and prints the state rows, cycler FSM reports and the secondary-flow
  series; `extract-window.txt` is its output.
- `boot.log` — the window scada's stdout/stderr from
  `/tmp/spruce-admin-panel/`; the dispatch, cycler, expander and pico
  POST lines.
- `flow.log` — the snapshot watcher's output; `flow_watch.py` is the
  watcher, kept as run (see its docstring for what is wrong with it).

Regenerate the extract from the instances:

    ../../gridworks-scada/gw_spaceheat/venv/bin/python extract_window.py > extract-window.txt

There is no `gw.readings` instance; the flow series is inside the
report events.

## Afternoon window (George on site, 13:25–)

Findings distilled in the spruce-admin-rig spoke; this section is the
record. Second run of the same rig: scada from `~/envs/dev.env` in the
background (bound 4 h, restarted 14:45 after the picos' 5 V supply was
reconnected, 14:54 at `cdce340b` for the hp-boss boot fix, 15:20 after
the relay-stress rerun on the replaced gw108), the panel in tmux on
the box.

- 14:24 window opened; picos dark (5 V supply unplugged after the board
  swap), hp-boss row `?` (no boot state report).
- 14:41 `start_api.sh` on port 8000 for two minutes with the scada
  stopped: all six picos posted within a minute of the supply returning
  (`rig-log/afternoon/api-test.log`).
- 14:54 `cdce340b` on the box; hp-boss reports `HpOff` at boot, row has
  a button; TurnOn/TurnOff/RebootPicos all answered.
- 15:02–15:10 charge valve OpenValve: pin high, store-flow 0, secondary
  3.96 gpm on the distribution path; DAC 5.0 V → 4.00 gpm.
- 15:14–15:18 relay stress B2/F2/A2 (`../2026-09-08-spruce-relay-stress-board2/`).
- 15:23–15:35 FSV 2091 = 1; TurnOn ×3; RIB red; hp-ctrl-box 6–8 W,
  hp-odu 62–70 W throughout (`egauge_live.py` reads); units
  power-cycled ~15:30, 2091 still 1.
- 15:32:29 TurnOn; 15:35:30 compressor start (app pressed on at the
  same time, screen "controlled by thermostat"); 15:37:08 TurnOff,
  odu 21 W by 15:38:00.
- ~15:41 app settings changed on site; screen now "mode: cool".
  15:40:47 TurnOn, no start in five minutes (EWT 13.3 °C); ~15:45:45
  app on, ctrl box 104 W at 15:46:00, odu to 1584 W; 15:48:06 TurnOff
  ignored; 15:51:30 compressor off on the cooling water law
  (LWT 8.1 °C at 15:50:30, app "water law temp").
- Journal DB pull (`pull_readings.py`, Aug 8 to Sep 8, hp-ewt +
  hp-odu-pwr): 1907 runs, 115 h, EWT at start median 51 °F, min 46 °F.

Folder additions (GENERATED by this window, on the box):

- `rig-log/afternoon/boot-*.log` — the window scada's stdout per run
  (`boot-1520-live.log` was still being written when copied).
- `rig-log/afternoon/snapshots.log` — every snapshot to admin, 30 s,
  `mosquitto_sub -F "%U %t %p"` on the box mosquitto (raw wire form).
- `rig-log/afternoon/api-test.log` — the fake pico API's two minutes.
- `rig-log/afternoon/stress.log` — the relay-stress rerun's console.
- `rig-log/afternoon/egauge_live.py` — direct eGauge read with the
  layout's register map; run from the box `starter-scripts` venv.
- `instances/afternoon-events/` — the scada's persisted upstream events
  (report.event every 5 min, problems, comm) from the experiment paths
  root; copied at 15:32 while the window was live, so a final copy at
  restore supersedes it.
