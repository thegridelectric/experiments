# admin reboots the picos, local sim (2026-09-07)

Status: Verified · Pass 0 · Updated 2026-09-07 · Reviewed 2026-09-07@b095261c

> What this is: the dev-broker rung of the pico-cycler command. The real
> admin client, over the dev broker, asks the pico-cycler of a locally
> running sim Nolan scada to reboot the picos, while the sim picos also
> die and come back on their own; the journal-bound `report` stream is
> the evidence. Rung 1 is `tests/actors/test_pico_cycler_command.py` and
> `tests/actors/test_admin_reboots_picos.py`.

## Why

The cycler now stays awake under admin and takes one command from its
boss (scada `1229636c`, gwadmin `7997fc9a`). The in-process tests stop
at the relay open. What no test shows: the relay actually cycling on a
broker, the sim picos losing power and rebooting behind it, the roster
rows and the cycle's reports reaching the journal-bound `report`, and
the command's `TriggerId` surviving the whole loop to the cycler's
`fsm.full.report`. The hub's bar (`EDD: yes`) is this run.

## Setup

Dev broker `gw-dev-rabbit` up (MQTT 1885, TLS off). Scada from
`gridworks-scada` at the working-tree commit named in Found, the nolan
authored pair (`tests/config/gw.nolan.layout.json`, two
`sim.pico.tank.module.component.gt` tanks with `SimLifeS` 120 /
`SimRebootS` 20, alias `d1.isone.me.versant.keene.spruce.scada`), admin
link on, pico-cycler state logging on, `seconds_per_report` shortened to
60 so the journal-bound reports arrive each minute:

```sh
cd gridworks-scada
export PYTHONPATH=$PWD/gw_spaceheat
SCADA_ADMIN__ENABLED=true SCADA_ADMIN__HOST=localhost SCADA_ADMIN__PORT=1885 \
SCADA_ADMIN__USERNAME=smqPublic SCADA_ADMIN__PASSWORD=smqPublic \
SCADA_PICO_CYCLER_STATE_LOGGING=true SCADA_SECONDS_PER_REPORT=60 \
  timeout 540 gw_spaceheat/venv/bin/gws run > ../experiments/2026-09-07-admin-reboots-picos/scada.log 2>&1 &
sleep 25
gw_spaceheat/venv/bin/python ../experiments/2026-09-07-admin-reboots-picos/admin_reboots_picos.py \
  ../experiments/2026-09-07-admin-reboots-picos/admin-drive.log \
  ../experiments/2026-09-07-admin-reboots-picos/broker-capture.jsonl
```

The driver uses the admin package's own `AdminClient` with the
`RelayWatchClient` subclient and calls `send_reboot_picos`, the method
the TUI's Reboot picos button calls, so the wire shape is the button's.
A second plain MQTT subscription on `gw/#` captures everything the scada
publishes on its gridworks link (the `report`s the journal would keep).

## Protocol

1. Boot the scada; its boot cycle (`Startup`) runs at t≈3 s.
2. Driver links as admin at t≈25 s and watches for 180 s: the sim picos,
   rebooted by the boot cycle, post for 120 s and go silent, the cycler
   sees them flatline and cycles on its own (`PicoMissing`).
3. Driver sends `reboot.picos` through `send_reboot_picos`. If the
   cycler is mid-cycle the command is ignored by design; the driver
   checks the cycler's state through a snapshot and re-sends every 20 s
   until one is taken, then waits for the cycler's `fsm.full.report`.
4. Release admin; stop.

**Pass.** (a) Admin side: the cycler's `fsm.full.report` carries the
dispatch's `TriggerId`, entered through `ShakeZombies`, ending
`ConfirmRebooted`. (b) Broker side, in `report.StateList`: a sim pico's
`single.pico.state` row Flatlined before the self-provoked cycle and
Alive after it; vdc-relay open then closed inside the commanded cycle.
(c) `report.FsmReportList` holds the boot cycle entering through
`Startup`, the self-provoked one through `PicoMissing`, the commanded
one through `ShakeZombies` under the dispatch's id.

## Found — PASS on the journal side, with two scada fixes and one gap

Four runs. Runs 1–3 on scada `7997fc9a` plus the working-tree fixes
below (run 1 without them; runs 2 and 3 with the relay fix; the cycler
fix was written after run 3). Run 4 on `b095261c`, both fixes landed:
the confirming run.

**Run 4 (17:24–17:30, `run4-*`): every cycle confirms on the sim
reboot.** Three cycles, each entering through its own event and each
confirming 20.2–20.3 s after its close (`SimRebootS` 20), none early:
`Startup` (`ab199d5f`) closed 17:24:56.06, live 17:25:16.09;
`PicoMissing` (`f8ce4277`) closed 17:27:23.09, live 17:27:43.28, with
both pico rows Flatlined at 17:27:18.08 and Alive at 17:27:43.28;
`ShakeZombies` under the dispatch's own id `fe4d0489` closed
17:28:20.07, live 17:28:40.35. The command was taken on the first
send, one commanded cycle only (runs 2–3 had re-sends). Pass
conditions (a), (b), (c) all hold on `run4-report-events.txt`. The
three cycles are 65 s and 57 s apart, both inside the old 60 s wait, so
the run exercises exactly the overlap fix 2 closes.

**Pass conditions, from the persisted `report.event`s
(`run3-report-events.txt`, instances under `instances/`):**

- (c) The boot cycle entered through `Startup` (15:33 report, trigger
  `220374ab`); the self-provoked cycle through `PicoMissing`
  (`ac456bb4`); the commanded cycle through `ShakeZombies` under the
  dispatch's own id `6a7f5a24`, the id the driver logged at 15:35:49.
- (b) `buffer` and `tank1` rows Flatlined at 15:34:52.592, a millisecond
  before the cycler's RelayOpening row, and Alive again at 15:35:17.89,
  twenty seconds after the relay closed (`SimRebootS`). vdc-relay open
  at 15:35:49.859 and closed at 15:35:54.866 inside the commanded cycle.
- (a) The cycler's `fsm.full.report` under the dispatch's id, entering
  `ShakeZombies` and ending `ConfirmRebooted`, is in the 15:36 report.

**Fix 1, found by run 1: a GPIO relay on a simulated board never
answered its boss.** `Relay._gpio_actuate_and_report` returned before
the pin report and the full report when `GPIO` is `None`. The relay's
own state committed (snapshot showed RelayOpen) but the cycler waited
forever in RelayOpening; no sim cycle had ever completed. Fixed to skip
only the pin write; `tests/actors/test_relay_gpio_sim.py`.

**Fix 2, found by run 2 and reproduced to the second in run 3: the
cycler's 60 s reboot wait is not tied to its cycle.** The self-provoked
cycle closed at 15:34:57.6; its `_wait_for_rebooting_picos` fired at
15:35:57.6 while the commanded cycle sat in PicosRebooting and confirmed
it, 2.7 s after that cycle's close and 17 s before the sim picos could
have posted. Run 2 showed the same arithmetic twice. Fixed: both waits
capture the cycle's `TriggerId` when spawned and stand down if another
cycle is running when they fire; two tests in
`tests/actors/test_pico_cycler_command.py`.

**Gap: admin gets no acknowledgement of its command.** The cycler's
`fsm.full.report` goes to the primary scada and rides only the
journal-bound `report`; nothing is forwarded on the admin link, and no
`single.machine.state` for the cycler reaches admin either. Admin sees
its command only through snapshots (the cycler's `LatestStateList` row).
The driver's first pass-(a) check waited on the admin link and so
re-sent twice (three commanded cycles, `893e7447` and `8cb24235` after
the first); the driver now judges the admin side by snapshot state and
leaves the id check to `collect_events.py`. Whether the TUI should get a
report back is a design question for the spoke.

**Also seen, missed until 2026-09-07 evening.** Every run's scada log
carries `Trouble with SendLayout: 'NoneType' object has no attribute
'component'` at each admin link-up. It is the `send.control.capabilities`
reply failing (the log label is the neighbouring branch's): the nolan
layout has no `relay-multiplexer` node and the capabilities word
requires one, so the real TUI shows no relays or DACs for this scada.
The driver never saw it because it judges by snapshots. The scada-side
fix belongs to the krida-retirement work, not this rung.

**Also seen.** With `SimLifeS` 120 the picos die every two minutes, so
the cycler runs a self-provoked cycle every ~2.5 min; a real house's
rhythm is another knob. Persisted `report.event`s carry every pico row
and cycle; nothing is lost between the actor and the journal path. The
scada's LTN link never went active (no LTN running), so the reports sat
in the event persister rather than on the broker; `broker-capture.jsonl`
holds only snapshots, single readings, the command tree and the admin
traffic.

## Timeline (laptop clock, ET)

- 15:24 run 1: boot; cycler stuck in RelayOpening after `Startup`;
  killed at 15:26 (`run1-*`).
- 15:27:05 run 2 boot cycle completes in 25 s (relay fix in tree);
  15:29:32 self-provoked cycle; 15:30:29 command taken; 15:30:37 stale
  confirm (+3 s); driver re-sent on a wrong taken-check; killed 15:31
  (`run2-*`).
- 15:32:25 run 3 boot cycle (`Startup`); 15:32:50 picos back.
- 15:34:52 both sim picos flatline; cycle; 15:35:17 picos back.
- 15:35:49 admin dispatch `6a7f5a24` taken; relay open 15:35:49.86,
  closed 15:35:54.87; 15:35:57.6 stale confirm from the earlier wait.
- 15:37:20 and 15:38:51 driver re-sends (`893e7447`, `8cb24235`); both
  cycles ran and confirmed at +20.7 s, the genuine pico reboot.
- 15:40:25 release; 15:41:35 driver done; scada stopped.
- 17:24:46 run 4 boot on `b095261c`; 17:24:56 boot cycle closes; 17:25:16 picos back.
- 17:27:18 both sim picos flatline; cycle closes 17:27:23; 17:27:43 picos back.
- 17:28:15 admin dispatch `fe4d0489` taken; relay open 17:28:15.06, closed 17:28:20.07; 17:28:40.35 PicosLive (+20.3 s).
- 17:28:47 release; 17:29:57 driver done; scada stopped.

## Analysis notes

- Report rows are stamped by the scada; `collect_events.py` prints them
  in ET. Row handles are the cycler's live handle at the time
  (`auto.pico-cycler` before the command, `admin.pico-cycler` after).
- A confirm within 20 s of a close cannot be the sim picos
  (`SimRebootS` 20); before fix 2 it is the earlier cycle's timer.
- Pico rows appear only on flips; a commanded cycle with healthy picos
  emits no pico rows.

## Folder contents & experimental method

All data here was GENERATED by this run against a local sim scada on
the dev broker (nothing in the journal DB or S3; a re-run makes a new
dataset). No deployed service was touched.

- `admin_reboots_picos.py` — the driver; the reproducer.
- `collect_events.py` — copies the scada's persisted `report.event`s for
  a window into `instances/` and prints the pico-cycler evidence table.
- `instances/HHMM-report.event-004.json` — runs 3 and 4's persisted
  report events, byte for byte as the scada wrote them (sema instances).
- `run3-report-events.txt` — `collect_events.py 15:32 15:42` output.
- `run4-report-events.txt` — `collect_events.py 17:24 17:32` output;
  `run4-notes.txt` the run's wall-clock marks.
- `runN-admin-drive.log` — the driver's timestamped notes per run.
- `runN-broker-capture.jsonl` — every message seen on `gw/#` per run.
- `runN-scada.log` — the scada's stdout per run.

Regenerate: the commands under Setup, then
`collect_events.py <start> <end>` for the run's window.
