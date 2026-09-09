# five-v-boss-hold, 2026-09-08 to 2026-09-09

Status: Verified · Pass 0 · Updated 2026-09-09 · Reviewed 2026-09-09@4bb46035

> What this is: the hold on the picos' 5 V above the pico-cycler,
> driven through the admin surface, first on the dev broker against a
> sim Nolan scada (runs 1 to 4, 09-08) and then from `gwa watch spruce`
> on the real spruce gw108 (the window, 09-09). Verdict in "Found".

## Why

On site the 5 V had to be pulled by hand for a pico swap: the panel
could reboot the picos but not hold them dark. five-v-boss is the
command node that holds the relay directly while the cycler sits
dormant. The in-process test (`tests/actors/test_five_v_boss.py`)
shares a wall clock and a backdoor transport, so the dev-broker rung
puts the hold on a real broker with real timing, and the spruce window
puts it on real picos with the 5 V measured at the board. The window is
also the first boot of a scada that reads a `ta.deed`.

## Setup

**Dev-broker side (runs 1 to 4).** Scada `4daec1ab` on
`jm/spruce-unlimbo` plus the working-tree fixes each run found; run 4
is the confirming run with all three in (`6cdf8a1d`). The 09-07 setup
(`../2026-09-07-admin-reboots-picos/README.md` "Setup"): dev broker
`gw-dev-rabbit` (MQTT 1885, TLS off), the nolan authored pair
(`tests/config/gw.nolan.layout.json`, two sim tanks with `SimLifeS` 120
and `SimRebootS` 20), admin link on from the repo `.env`, pico-cycler
state logging on, `seconds_per_report` 60. The driver
(`five_v_boss_hold.py`) uses the admin package's own `AdminClient` with
the `RelayWatchClient` subclient and calls `send_command("five-v-boss",
…)`, the method the panel's row buttons call, so the wire shape is the
panel's; a plain MQTT subscription on `gw/#` captures the scada's
gridworks-link traffic.

**Spruce side (the window).** Scada `4bb46035` on `jm/spruce-unlimbo`,
pulled into the box's `~/gridworks-scada-unlimbo`. The deployed service
(`~/gridworks-scada`, `30fc7f59`), its restart timer and
`spruce-summer-hack` were stopped for the window and restarted after.
Isolation as `../2026-09-08-spruce-admin-panel/`: the window scada
boots through `~/experiments/2026-08-10-ads-declared-rate/window_boot.py`
from `~/envs/dev.env` (real spruce identity, dev-broker creds,
upstream through the laptop's `ssh -R 1885` tunnel, paths root
`scada-experiment`). Sockets during the window: the tunnel on
`::1:1885`, the admin link on the box's mosquitto `::1:1883`, the local
link on `192.168.2.200:1883`; nothing reached the hw1 broker. JM drove
the panel and the meter; the session ran the box.

Artifacts consumed by the window (`~/.config/gridworks/scada-experiment/`):

| file | type | sha256 (first 16) | mtime |
| --- | --- | --- | --- |
| `hardware-layout.json` | `gw.nolan.layout` (three-tank layout of 09-09) | `5376f76e09673955` | 2026-09-09 09:19:05 |
| `operational-params.json` | `gw.nolan.operational.params` | `eb4a7cb4480f7d52` | 2026-09-09 09:19:08 |
| `ta-deed.json` | `ta.deed/000`, ValidatedRealAssetAndGps | `b65c847a5a9da2d4` | 2026-09-09 09:48:49 |

## Protocol

Dev-broker side, from `gridworks-scada`:

```sh
export PYTHONPATH=$PWD/gw_spaceheat
E=../experiments/2026-09-08-five-v-boss-hold
SCADA_PICO_CYCLER_STATE_LOGGING=true SCADA_SECONDS_PER_REPORT=60 \
  timeout 960 gw_spaceheat/venv/bin/gws run > $E/run4-scada.log 2>&1 & SPID=$!
sleep 25
gw_spaceheat/venv/bin/python $E/five_v_boss_hold.py $E/run4-admin-drive.log $E/run4-broker-capture.jsonl
kill $SPID
cd $E && uv run python collect_events.py collect run4 <start HH:MM> <end HH:MM> ~/.local/share/gridworks/scada/event/$(date -I)T00:00:00+00:00
```

Stop the scada by PID: a `pkill -f "gws run"` from a wrapper whose own
command line names it kills the wrapper.

1. Boot; watch 150 s for the boot cycle and the sim picos' first posts.
2. `TurnOff`: an ack; five-v-boss walks TurningOff to FiveVOff,
   `vdc-relay` moves under five-v-boss and reads RelayOpen, the cycler
   reads Dormant.
3. Hold 150 s (past `SimLifeS` 120): no relay event, no cycler transition.
4. `TurnOn`: TurningOn to PicoCycler, the relay back under the cycler
   and RelayClosed, cycler PicosLive, picos re-POST.
5. `TurnOff` again, then `admin.release.control`: the scada's
   AutoWakesUp restores the 5 V under a self-minted id.

Spruce side:

1. Laptop: push `jm/spruce-unlimbo`; box: pull `~/gridworks-scada-unlimbo`.
2. Laptop: `ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 spruce`.
3. Box: `sudo systemctl stop gwspaceheat-restart.timer gwspaceheat spruce-summer-hack`, then a 30 min window:

       mkdir -p /tmp/spruce-five-v-boss
       cd ~/gridworks-scada-unlimbo/gw_spaceheat && SCADA_PICO_CYCLER_STATE_LOGGING=true setsid nohup timeout 1860 venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py 1800 ~/envs/dev.env > /tmp/spruce-five-v-boss/boot.log 2>&1 < /dev/null &

   (`../spruce_window.sh on` does steps 2 and 3 now.)
4. Laptop: `gridworks-scada/gw_spaceheat/venv/bin/gwa watch spruce`; the five-v-boss row shows PicoCycler.
5. TurnOff from the row: TurningOff, FiveVOff, cycler Dormant, the meter on the 5 V rail reads 0.
6. Hold past a pico flatline period: roster rows go Flatlined, nothing cycles.
7. TurnOn: TurningOn, PicoCycler, cycler wakes, picos re-POST.
8. TurnOff again, release admin, the 5 V comes back on its own (not
   reached: admin was released from PicoCycler instead).
9. Restore: `pkill -f "[w]indow_boot.py"`, confirm the deployed event
   dir holds nothing window-born, start the three services. Copy the
   boot log here and the window paths root's pending event dir
   (`~/.local/share/gridworks/scada-experiment/event/<date>T00:00:00+00:00/`)
   to the laptop, then `uv run python collect_events.py collect window
   <start> <end> <that dir>`; remove both from the box.

Pass, both sides: every step's states as above; `report.FsmReportList`
holds five-v-boss's full reports under the dispatch ids; every
transition a `five.v.boss.state` row in `report.StateList`; an ack on
the admin link for each command.

## Found

PASS on both sides. The five-v-boss machine does what the
pico-cycler-command spoke says at every step, on the dev broker and on
the real house.

- **The hold, dev broker (run 4).** TurnOff to FiveVOff in 3 ms with
  the cycler Dormant and the relay open under `admin.five-v-boss`; a
  150 s hold with no relay event and no cycler transition; TurnOn to
  PicoCycler with the relay back under the cycler and the cycler
  PicosLive; release from FiveVOff restored the 5 V under a self-minted
  id inside one millisecond. `FsmReportList` carries all four full
  reports under their ids.
- **The hold, spruce.** TurnOff at 10:11:21 walked to FiveVOff in
  27 ms; five picos flatlined during the hold (fancoil, floor1, pipes1
  at 10:11:46; buffer, tank1 at 10:13:06) and the dormant cycler cycled
  nothing; TurnOn at 10:15:58 reached PicoCycler in 12 ms and woke the
  cycler; admin release at 10:16:25 found "nothing to restore" in
  PicoCycler. The four BTU picos never flatlined in 4.5 min off: their
  actors' missing threshold is longer than the hold.
- **Three scada fixes found by the dev rung** (`6cdf8a1d`): gwadmin's
  row gathers every command interface on its node (run 1 refused
  TurnOff because the second interface overwrote the first); five-v-boss
  labels both halves of a path by its command (run 2); the cycler's
  `GoDormant` goes through `trigger_event` so its row is sent at the
  transition rather than on the periodic report (run 3).
- **Three picos never posted on spruce.** fancoil, floor1 and pipes1
  have no channel readings in either persisted report of the window.
  They are in the three-tank layout of 09-09 and absent from the
  deployed scada's log over the two days before. After TurnOn, buffer
  and tank1 re-POSTed and those three did not, so the cycler ran two
  reboot cycles (10:16:46, 10:17:51) on their behalf. If they are not
  on the wall, the deployed scada cycles the live picos for them
  indefinitely.
- **The panel offers one command on the five-v-boss row.** Only
  TurnOff appeared in PicoCycler; RebootPicos never did.
  `RelayWidgetConfig.next_command` returns the first command whose
  target state differs from the observed one, and RebootPicos leads
  back to PicoCycler, so it is never chosen; the row has a single
  button in any case. Queued in the spoke, with indenting the owned
  rows (pico-cycler, vdc-relay) under five-v-boss.
- **Deed read.** The window scada resolved `tadeed` to the deed beside
  the layout and booted without complaint.
- Minor: after a reparent a node's snapshot handle is stale until its
  next state row (run 3, and the panel's vdc-relay row on spruce);
  five-v-boss logs "Ignoring reply" for each vdc-relay ack by design,
  acting on the relay's report; at boot on spruce hp-boss logged an
  unexpected `gw.dispatch.ack` from hp-scada-ops-relay (the HpOff boot
  hack, `cdce340b`).

## Timeline

Dev broker, 09-08, ET:

- Run 1: stopped at step 2, the admin client refused TurnOff (`five-v-boss takes ['RebootPicos']`). Fixed before run 2.
- Run 2 (19:05 to 19:17): every state as the protocol says. TurnOff acked 19:08:46; TurnOn 19:12:48, then 1.6 s later a PicoMissing from the buffer's dark sim pico sent the woken cycler through a full cycle; second TurnOff 19:15:02; release 19:15:06 restored the 5 V. The driver's tree checks failed on their own bug (it looked for `new.command.tree` on the admin link; it rides `gw/#`). Fixed for run 3.
- Run 3 (19:18 to 19:30): the tree reads through. The cycler's Dormant row rode only the periodic report, so the driver read step 2 and the hold as FAIL while the scada log shows `Going Dormant!` at the command; and the driver let a stale snapshot handle overwrite the published tree. Both fixed before run 4.
- Run 4 (19:29 to 19:37): PASS on every step. TurnOff 19:32:37, hold to 19:35:11, TurnOn 19:35:11, TurnOff 19:35:57, release 19:36:01. No PicoMissing cycle followed TurnOn this time.

Spruce, 09-09, ET:

- 10:09:16 window scada up; boot cycle; PicosLive 10:09:31. 10:10:06 admin link active.
- 10:11:21 TurnOff. 10:11:46 three flatlines. 10:13:06 two more.
- 10:15:58 TurnOn. 10:16:25 admin released. 10:16:46 and 10:17:51 cycler reboot cycles for the three silent picos.
- 10:18:28 window scada killed; deployed services restarted.

## Analysis notes

Times are from the scada logs and the admin-link RX lines; the dev
driver's own PASS stamps trail by its 2 s poll and are not latencies.
The persisted events are the ones still pending upstream ack when the
scada stopped, so `instances/` holds the 1-minute reports of run 4
(19:29 to 19:37) and the two 5-minute reports of the spruce window
(10:10, 10:15; the 10:20 report never ran). Machine-state rows live in
each report's `StateList`, full FSM reports in `FsmReportList`. The
files are `report.event` instances (not envelopes), decoded strict and
re-emitted through this repo's sema snapshot (`report.event` 003 and
004 in the seed).

## Folder contents & experimental method

GENERATED by this experiment: the dev-broker files came from a sim
scada on the laptop, the spruce files from a window scada on the box
with the deployed scada and the summer hack stopped. No store holds
any of it (the dev broker has no journal consumer; the window's
upstream was the dev broker); a re-run produces a new set. Runs 1 to 3
were pruned to their findings above; run 4 and the window are the
evidence behind the stamp.

- `five_v_boss_hold.py` — the dev-broker driver (protocol above, PASS/FAIL per step, SUMMARY at the end).
- `collect_events.py` — decodes the scada's persisted `report.event`s for a window through the sema snapshot, writes them to `instances/` under the instance grammar, and prints the five-v-boss digest from the typed fields.
- `run4-admin-drive.log`, `run4-broker-capture.jsonl`, `run4-scada.log`, `run4-driver-stdout.txt` — run 4's admin-link view, everything on `gw/#`, the scada's stdout, the driver's stdout.
- `run4-report-events.txt` — the digest `collect_events.py` printed for run 4.
- `spruce-boot.log` — the window scada's stdout on spruce, cycler state logging on.
- `instances/<scada alias>-run4.<HHMM>-report.event-004.json` (9), `instances/<scada alias>-window.<HHMM>-report.event-004.json` (2) — the persisted reports.

Regenerate: the Protocol above, end to end, on each side; the
instances come from a local copy of the scada's pending event dir
(`collect_events.py collect …`, laptop side; from a box, scp that dir
first). The five-v-boss digest, through the snapshot:

    uv run python collect_events.py digest instances/*.json
