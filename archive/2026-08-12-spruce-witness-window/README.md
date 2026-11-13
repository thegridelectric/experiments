# 2026-08-12 · spruce-witness-window

First witnessed scada actuation sequence on spruce: `NolanLocalControl`
boots into Normal, runs the scripted witness (fancoil circuit takeover +
call, secondary pump start/stop), segues to Monitor. Two windows the same
morning, both inside the 07–12 on-peak block (hack failsafe posture = the
window posture, so zero cooling stakes). Window #1 died on a laptop-catchable
bug and leaked one event to prod (forensics + cleanup below); window #2,
after the fixes, PASSED end-to-end with zero glitches and delivered both
behavioral measurements.

## Why

The relay path's EDD gate (spruce-unlimbo, summer-local-control build step
6/8): pin-readback command-and-confirm on the real expanders, warm-takeover
boot adoption beside the hack's latched holds, and the system-working
harness's first two experiments — the distribution response behind the
Caleffi zone-control box, and the secondary pump's flow across the HX.

## Setup (reproducer)

- **Code under test:** gridworks-scada `jm/spruce-unlimbo` — window #1 at
  `690d584e`, window #2 at `1ccb4c1a` (the fixes). tlayouts `jm/spruce`
  `15c7459`; artifacts md5 `7984f04899fbf6da92dbea05a6ada392`
  (gw.nolan.layout.json → `~/.config/gridworks/scada-experiment/hardware-layout.json`)
  and `d10fcd9435cd7bd51ac276f2979eb875` (ops params, sibling dir).
- **Harness:** `../2026-08-10-ads-declared-rate/window_boot.py` (600 s
  bound; since window #2's fix it builds `WindowScadaApp` — the
  `paths_name()` subclass is the ONLY paths-root override that survives app
  construction — and refuses to boot if event/log dirs resolve outside
  `scada-experiment`).
- **Isolation:** dev broker only — laptop `gw-dev-rabbit` via
  `ssh -f -N -R 1885:localhost:1885 spruce`; `~/envs/dev.env` (no hw1
  creds). Window protocol: `gwspaceheat-restart.timer`, `gwspaceheat`, and
  `spruce-summer-hack` stopped; hack exits to failsafe with zone holds
  latched.
- **Watch:** `snap_watch.py` with `MQTT_HOST=localhost MQTT_PORT=1885` +
  dev creds (tmux `window`). NOTE: it prints only `LatestReadingList`;
  relay states ride `LatestStateList` on every snapshot and are invisible
  to it (patch queued in starter-scripts).

## Window #1 — 10:33–10:38 ET: FAIL (bug), one-event leak (cleaned)

- Boot 10:33:38. Bus guard: **warm takeover witnessed on both expanders**
  (config regs already outputs; holds left driving) — first real-hardware
  evidence for adopt-or-init.
- **Killer:** `scada_data.py:195` `capture_seconds` walked every
  component ConfigList assuming channel-shaped entries and hit the DAC
  writer's `i2c.dac.channel.config` at the first snapshot tick (10:34:00.000
  exactly); the catching loop retried at sub-ms cadence — **420,250 log
  lines in ~4 min** (`window1-boot-2026-08-12.log.gz`), starving the event
  loop. No snapshots were ever generated; the witness never ran its first
  step. Third instance of the same walker-bug class; the pinned Nolan test
  fixture has no DAC writer, which is why 189 green tests missed it.
- **The leak:** `SCADA_PATHS__NAME` in the env file was silently discarded
  (every app-construction path re-applies `cls.paths_name()`), so the
  window shared the deployed scada's roots. The window's LTN link never
  left `awaiting_peer` (no LTN on the dev broker), so its pending events
  died in memory with the process — EXCEPT the SIGTERM shutdown event
  written while dying (14:38:40.97Z), which landed in the shared event dir
  and rode the deployed scada's startup reupload (16 events on disk, 23
  total, completed 14:38:41.25Z) to the prod broker.
- **Forensics + cleanup:** journal DB verified clean (event envelopes are
  not journaled). Exactly ONE window-born object reached the S3 eventstore:
  `hw1.…spruce.scada-gridworks.event.shutdown-1786545520972-hw1.ear.json` —
  a prod-vocabulary envelope (MessageId/TimeCreatedMs/Src/Reason), zero
  staging content. Archived here (`window-shutdown-event.json`), then
  deleted from `s3://gwdev/hw1__1/eventstore/20260812/`. **No staging-word
  instances reached prod or S3** — snapshots/layout.lite (the staging-typed
  payloads) never existed or went only to the dev link. Key-listing used
  for the sweep: `spruce-keys-today.txt` (eventstore keys embed
  TimeCreatedMs; the 6 other window-span keys are the LTN pinging the down
  scada — left in place).

## Fixes between windows (scada `1ccb4c1a`)

`ChannelConfigBase` isinstance filter in `capture_seconds`; the
spruce-artifact sim-boot regression test (suite boots the real artifact and
builds a snapshot — would have caught window #1 on the laptop); the
`WindowScadaApp` isolation subclass + boot refusal; canary tests pinning
both the paths-name discard behavior and the subclass mechanism.

## Window #2 — 11:25–11:35 ET: PASS

Boot 11:25:21. Isolation asserted (logs + the one persisted event under
`scada-experiment/`; prod untouched). Warm takeover again; snapshots flowed
all window (30 s cadence, `window-snapwatch-0812.log`). Witness timeline,
every actuation pin-confirmed, zero glitches:

| time | step |
| --- | --- |
| 11:25:52 | fancoil takeover (zone5 failsafe → Scada) |
| 11:26:07 | fancoil call ON (ops closed) |
| 11:27:37 | fancoil call OFF |
| 11:27:52 | release to stat (failsafe → WallThermostat) |
| 11:28:07 | secondary pump ON |
| 11:29:07 | secondary pump OFF |
| 11:29:22 | witness complete → MonitorOnly → Monitor |

**Measurements** (30 s snapshot cadence bounds the precision):

- **Distribution response through the Caleffi zone-control box:** call ON
  11:26:07 → `dist-flow` 158 (1.58 GPM) in a reading taken ~11:26:36 —
  **response ≤ 29 s**, inside the predicted seconds-to-half-minute band.
  Call OFF 11:27:37 → flow 0 by ~11:27:42 (**off ≈ 5 s** — fast).
- **Secondary pump / HX flow:** pump ON 11:28:07 → `secondary-flow` 746
  (7.46 GPM) by ~11:28:12 — full flow in seconds, matching the ~7.5 GPM HX
  target at the 65 % speed held by the DAC's EEPROM power-on default (the
  DAC write path was not exercised). OFF 11:29:07 → ~0 by ~11:29:11.
- **Instrument notes:** `dist-pump-pwr` flat at 1 W all window — not a
  usable observable yet; `secondary-pump-ct` flat at 167 regardless of pump
  state — channel suspect (CT wiring/scaling).
- 8/8 zone gw channels populated at the bound. Zone 1/2/4 holds never
  moved.
- Blemish (operator, not system): restore was run at 11:34:33 — 48 s
  before the 600 s bound — from a misread clock, giving ~46 s of hack +
  window-reader overlap (two `i2c-thermistor-read-failed` warnings, no
  relay contention, postures agreed).

## Lessons → mechanical guards

1. **Overrides are verified, not assumed** — window #1's leak came from an
   env override that silently didn't apply. Guard: the harness now refuses
   to boot outside its isolation root; canary tests pin the mechanism.
2. **Suite boots the real artifact** — fixture-only coverage missed a
   boot-killing bug in a component the fixture lacked. Guard: the
   spruce sim-boot test.
3. **Restore gates on the `window done` line in the boot log** (or a dead
   process check), never wall-clock arithmetic. Guard: runbook step, next
   window.

## Verified (scoped claims)

- Adopt-or-init warm takeover on real hardware, ×2 boots: configured
  expanders left driving, latched holds inherited as confirmed state.
- Command-and-confirm relay path on the real expanders: 6 actuations
  across 3 vocabularies (`zone.call.source`, `change.relay.state` pair on
  ops/pump), 6 pin confirms, 0 mismatches, 0 retries needed.
- `NolanLocalControl` layout-family selection + scripted witness + segue
  to observe-only, on the box.
- The two behavioral numbers above, first-measured.
