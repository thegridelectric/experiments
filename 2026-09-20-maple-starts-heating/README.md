# maple-starts-heating, 2026-09-20

> What this is: field-support log of bringing maple out of Standby into
> Heating in BufferOnly on scada `main`: first with the Siegenthaler valve
> parked at full send and no SiegLoop actor, then from 14:58 with SiegLoop
> restored so the loop closes when the heat pump is off. Findings
> accumulate under "Found".

## Why

Maple sat in `SCADA_SYSTEM_MODE=Standby` since spring. For this heating
season it runs BufferOnly, LTN monitor-only, with the sieg valve fixed at full
send. Before the heat pump runs we need to know the valve is open, which
flows and powers we can trust, and what the scada can and cannot actuate.

## Setup

- Box `maple`: `gwspaceheat` systemd service, `~/gridworks-scada` on `main`
  @ `54f74302`, env `~/gridworks-scada/.env` (`SEASONAL_STORAGE_MODE=BufferOnly`).
- Layout from 14:58:54: the April layout, `UseSiegLoop: True`, restored from
  the copy kept on the box. tlayouts `main` @ `08d3f01` matches it. Until
  then:
- Layout: `gen_maple.py` with `use_sieg_loop=False`, variant `House0Sieg`
  (tlayouts branch `jm/maple-no-sieg-loop`), generated against scada `main`
  with the box layout as id source. Previous box layout kept beside it as
  `hardware-layout.2026-09-20-pre-no-sieg-loop.json`.
- LTN: tmux session `maple` on the `ltn` box, `LTN_MONITOR_ONLY=True`.
- Admin: `gwa watch` from the laptop. Observation: `maple_flow_watch.sh`
  (admin snapshots off the box's local mosquitto) plus the box journal.

## Found

1. **No scada control of the primary pump.** With relay 12 (primary pump
   failsafe) switched to Scada and relay 11 open, `sieg-send` held
   4.2–4.3 gpm for 3.5+ minutes (12:15:08 → 12:18:30). The failsafe relay is
   disabled at maple; believed to date from the Samsung → Mitsubishi heat
   pump swap.
2. **`primary-pump-pwr` cannot be read.** Journal DB: real readings (avg
   ~35–41 W, max 1004 W) through 2026-03-20 06:03, then ≤ 4 W ever since,
   including April days with `hp-odu-pwr` at 8–12 kW and `sieg-flow` > 5 gpm.
   Likely the same cause: the pump is embedded in the Mitsubishi, no CT.
3. **Sieg valve verified at full send.** See Timeline 12:07 → 12:14:30.
4. **Under `UseSiegLoop: True` the admin cannot move relays 14/15.** Their
   handle is `admin.sieg-loop.relay15`, so the panel's `admin.relay15` is
   ignored. With `UseSiegLoop: False` they answer to admin directly, and
   nothing in the scada moves the valve.
5. **`primary-flow` (derived, `sieg-send` + `sieg-flow`) is in the layout,
   same id, but has produced no value since the 12:11 restart.** Open. The
   derived-generator code is identical between `0f623987` (ran before) and
   `54f74302`. Its only reader on main is the store-discharge pump check,
   unused in BufferOnly.
6. **LTN `LTN_HP_MODEL` says Samsung; scada says `MitsubishiEcodan`.**
   Harmless while the LTN is monitor-only.
7. **Heat pump swap dated 2026-03-20 → 03-24.** Last real
   `primary-pump-pwr` 03-20 06:03; maple silent 03-20 09:23 → 03-24 13:00;
   ~370 W `hp-odu-pwr` blips 03-24/25; first real run 03-26 10:00 (6.6 kW);
   `MitsubishiEcodan` enters gridworks-scada 03-27 (`71ae4e68`).
8. **The eGauge answers without auth** at
   `https://egauge16103.egaug.es/cgi-bin/egauge?inst`: `03-hp-odu`,
   `02-hp-indoor`, `06-dist-pump-power`, `07-primary-pump-power` (0 W with
   4 gpm flowing). Its clock runs ~63 min behind.
9. **A cold start with an empty buffer falls to oil backup after 5 minutes.**
   BufferOnly's SystemCold test is "a critical zone ≥ 1 F under setpoint AND
   buffer empty" held for `SYSTEM_COLD_MINUTES = 5`. A heat pump charging a
   61 F buffer cannot clear either condition in 5 minutes, so with
   `SCADA_OIL_BOILER_BACKUP` at its default (True; unset in maple's `.env`)
   the scada hands the house to the boiler and turns the heat pump off. The
   boiler drew 0 W (September peak 49 W, so likely switched off for summer).
10. **scada main:** `layout_gen/flow.py:118` passes `component_display_name`
   uncalled, so hall-flow ComponentIds (`dist-flow`, `sieg-send`) re-roll on
   every layout regeneration.
11. **With `SCADA_OIL_BOILER_BACKUP=False` the heat pump stays on across
   the SystemCold mark, and the local-control state machine says it is not
   in `HpOn`.** Pulled readings: relays 5 and 8 moved at 12:31:53 (backup
   True) and did not move at 12:46:25 (backup False); relay 6 stayed
   closed from 12:23:49 to 13:26:26; `hp-odu-pwr` rose through the mark
   (5-minute means 390 W at 12:40, 1209 W at 12:45, 1873 W at 12:50, 5.0 kW
   by 14:00). The journal shows `Top State SystemCold: Normal ->
   UsingNonElectricBackup` and `GoDormant: HpOn -> Dormant` at 12:46:25.
   `trigger_system_cold_event` (`tou_base.py:361`) sends the normal node
   dormant whatever the backup setting, then `backup_actuator_actions`
   (`tou_base.py:416`) calls `turn_on_HP` from the backup node. So the
   BufferOnly machine reports `Dormant` while the heat pump runs under
   `auto.h.backup`, and nothing in either state records that it is on.
12. **With the valve at full send the primary pump cools the buffer top as
   soon as the heat pump stops.** Relay 6 opened 13:26:26 → 13:29:26
   (`buffer-depth1` had reached 103.2 F against the 102.9 F RSWT).
   `hp-odu-pwr` fell 2859 W → 95 W inside 4 s; `sieg-send` held 4.3 gpm
   throughout; `buffer-depth1` fell to 95.3 F by 13:38. The heat pump drew
   power again at 13:33:11, 3 min 45 s after relay 6 closed.
13. **`hp-idu-pwr` reports, and reads 0 W: its CT is still installed but
   is not attached to anything.** 28 readings in the window, all within
   ±2 W. `total_hp_pwr_w()` is therefore `hp-odu-pwr` at maple, and
   SiegLoop's Blind test (`sieg_loop.py:265`) has the data it asks for.
   The layout still declares the channel as a heat pump power.
14. **With `UseSiegLoop: True` restored, SiegLoop closes the loop when the
   heat pump is off.** Layout swapped back and scada restarted 14:58:54 on
   `54f74302` with local control in `HpOff`. At 15:02:59 SiegLoop went
   `Blind -> HpOff` and drove to full keep: `sieg-send` 4.28 → 0.02 gpm and
   `sieg-flow` 0 → 5.11 gpm between 15:03:19 and 15:04:24; movement
   complete 15:04:49 (100 s). `buffer-depth1` held 117.2–117.5 F across
   it. Not yet seen: a heat pump start through HpBoss's SiegLoopReady
   wait, and the move back to send once the heat pump has lift.
15. **SiegLoop spends the first four minutes after a restart in `Blind`,
   at full send.** `Initializing -> Blind` at 14:58:59, `Blind -> HpOff`
   at 15:02:59, with `hp-lwt`, `hp-ewt` and both power channels
   reporting. Cause not traced. It also assumes the valve starts at full
   keep, so its first move was a 110 s drive toward a full-send stop the
   valve was already on. And it reports valve state `SteadyBlend` after a
   completed full-keep move, not `FullyKeep`.
16. **A hall flow channel that stops reads its last small value, not 0.**
   `sieg-send` reported 4.28 → 3.01 → 1.65 → 0.21 → 0.02 gpm as the valve
   closed and then nothing more; the flow is zero. The pico is not the
   cause: with no ticks it posts an empty tick list every 7 s. The scada's
   `ApiFlowModule` drops it (`api_flow_module.py:596` on `54f74302`): on
   an empty tick list it publishes zero only when the last gpm is above
   `AsyncCaptureThresholdGpmTimes100` (20, so 0.2 gpm). At 0.02 it never
   does, and the five-minute synced report re-sends 0.02. `sieg-flow` at
   the other end of the travel shows the same shape in reverse. The same
   lines are on `jm/spruce-unlimbo` (`api_flow_module.py:646`).
17. **Maple's Mitsubishi defrosts in two phases, and for about two minutes
   of each defrost it draws under 100 W while commanded on.** 67 defrosts
   in 2026-03-26 → 05-15; see "Defrost profile".

## The 5-minute SystemCold mark

`LocalControlTouBase` moves `Normal -> UsingNonElectricBackup` when
`time_to_trigger_system_cold()` has held for `SYSTEM_COLD_MINUTES = 5`. For
BufferOnly that test is "a critical zone is more than 1 F under its setpoint
AND the buffer is empty". With `SCADA_OIL_BOILER_BACKUP=True` backup means
heat pump failsafe to aquastat and aquastat control to boiler, which turns
the heat pump off; with `False` backup calls `turn_on_HP`.

**Why it took 8 minutes from the 12:23:44 start, not 5.** Two things add to
the hold. The local-control loop ticks once a minute (every log line lands at
:53), so the hold is measured in whole ticks. And `is_system_cold()` answers
False while a zone has no temperature yet: the 12:23:53, 12:24:53 and 12:25:53
ticks all logged "All critical zones are at or above their effective
setpoint" while thermostat readings were still arriving after the restart.
The first cold tick was 12:26:53 (zone2-bedroom); five ticks later, 12:31:53,
it fired. So the mark is 5 minutes after the first tick that sees a cold
zone, which on a restart is 1–3 minutes after start.

**What the condition does not look at.** Whether the heat pump is already on,
whether the buffer is warming, or how long the heat pump has had. A cold
start with an empty buffer therefore always reaches the mark: no heat pump
lifts a 61 F buffer past the ~103 F RSWT, or a zone by 1 F, in five minutes.

**How to test it.** No test covers the hold or the top-state transition. On
the unlimbo branch `tests/actors/test_hydronic_shared.py` covers
`is_system_cold()` itself (including "false without a temperature"), and
nothing on `main` does. Two blockers for a simulated run:
`is_system_cold()` returns False whenever `is_simulated` is set, and the
hold reads `time.time()` directly. The local test that reproduces today's
field behaviour, in order:

1. Make the sim able to be cold: a settable simulated zone temperature and
   setpoint, replacing the `is_simulated` short-circuit.
2. Simulated House0 in BufferOnly, buffer at 61 F, one critical zone 2 F
   under setpoint, heat pump allowed on. Advance time past five ticks.
3. Assert with `oil_boiler_backup=True`: top state
   `UsingNonElectricBackup`, relay 5 to aquastat, relay 8 to boiler, heat
   pump off. This is what happened at 12:31:53 and the test should fail
   first if we decide that is wrong.
4. Assert with `oil_boiler_backup=False`: heat pump stays on across the
   mark. The 12:38:15 restart is the field run of this case.

Open design question the test should settle: should SystemCold hold off
while the heat pump is on and the buffer is rising?

## Defrost profile

`defrost_hunt.py` over the journal readings for 2026-03-26 → 2026-05-15
(51 days, after the heat pump swap). The hunt looks for the scada
commanding the heat pump on (relay 6 de-energized throughout), real lift
(≥ 2 C at ≥ 500 W) in the quarter hour before, then lift (`hp-lwt` −
`hp-ewt`) at or below zero. 152 such stretches, of three kinds:

- **defrost, 67** on 30 days: lift ≤ −5 C held ≥ 2 min with power dipping
  under 1 kW.
- **blip, 48**: under a minute, heat pump at full power (5–8 kW), lift −2
  to −6 C. A sensor transient, several on the half hour; not a change in
  what the heat pump is doing. Not chased here.
- **other, 37**: mostly shallow (lift 0 to −2 C) with power near zero, the
  heat pump stopping its own compressor while commanded on.

The 67 defrosts (median, with 10th–90th percentile or range where it
matters):

| | |
| --- | --- |
| Outdoor air at start | 0.2 C median; −10.2 to 7.5 C; 90 % under 3.5 C |
| Power in the 5 min before | 4.1 kW |
| Lift ≤ 0 lasts | 446 s (7.4 min); longest 608 s |
| Deepest lift | −12.3 C; worst −24.3 C |
| LWT falls by | 20 C (e.g. 48 → 28 C) |
| Mean power, start to recovery | 1.3 kW |
| Lowest power | 73 W |
| Longest stretch under 100 W | 121 s median, 132 s p90 |
| Longest stretch under 500 W | 137 s median, 255 s p90 |
| Start to lift back at 2 C | 476 s (7.9 min); p90 564 s |
| Defrost to defrost, same run | 49 min median, 90 min p90 (20 pairs) |
| Hour of day | 58 of 67 between 20:00 and 08:59 ET |

One defrost at 20 s steps (2026-04-01 01:13, outdoor −0.8 C): 5.9 kW →
480 W inside 40 s; 5 min at 480 W with LWT falling 47.9 → 28.7 C against an
EWT of 39 C (the heat pump is taking heat from the water); then 46 W for
2 min 20 s (compressor stopped, LWT drifting back to EWT); then 2.9 kW and
lift positive again 8 min after the start. The first-phase power varies
between defrosts (roughly 0.5–1.5 kW); the ~46–170 W stop of about 130 s is
in nearly all of them.

What it means for deciding "off" from power: a bare threshold under ~500 W
reads every defrost as off for 2–4 minutes, longer than the valve's 100 s
travel, so the loop would close and reopen inside each one. A real off
today fell from 2.9 kW to under 100 W in 4 s and stayed there. The two
differ in what the scada commanded and in how long the low power lasts
(p90 255 s, longest seen 950 s under 500 W).

Not settled by this data: what the valve should do during a defrost. At
full send the 28 C water goes to the buffer; at full keep the heat pump
draws its defrost heat from the small loop alone.

## Timeline

ET, 2026-09-20.

- 11:48 Scada found running `main` @ `0f623987` in Standby, layout
  `UseSiegLoop: True`; SiegLoop in `HpOff`, valve at full keep.
- 12:02:23 Admin `ChangeToKeepLess` to relay 15 ignored (handle
  `admin.sieg-loop.relay15`).
- ~12:01 New layout (`UseSiegLoop: False`) installed on the box.
- 12:07 Baseline: `sieg-flow` 5.00 gpm, `sieg-send` 0.00, relay 11 = 0.
- 12:11:24 Scada restarted in Standby on `54f74302`; StandbyLocalControl;
  relay 15 → SendMore, relay 14 energized (dormant), relay 6 energized (HP off).
- 12:11:43 `[sieg-btu] malformed BtuMeter parameters` — expected, picos are
  mid-upload.
- 12:12:49 Admin takes control; relay 14 de-energized (valve moving).
- 12:14:00 Mid-travel: `sieg-flow` 0.23, `sieg-send` 3.33.
- 12:14:30 Full send: `sieg-flow` 0.00, `sieg-send` 4.28.
- 12:15:01 Relay 14 energized (dormant).
- 12:15:08 Relay 12 → Scada; relay 11 open. Flow unchanged.
- 12:15:35 vdc relay cycled (1 s open).
- 12:22:00 Still 0.00 / 4.30; relay 12 back to 0.
- 12:23:44 Scada restarted with `SCADA_SYSTEM_MODE=Heating`;
  BufferOnlyTouLocalControl; 155-hour forecast obtained; relay 15 SendMore,
  relay 14 dormant; pico reboot triggered 12:23:51.
- 12:24:05 "Buffer Temps Available: False", blind 12 s (picos rebooting).
- 12:24:53 Buffer temps back (depth1 61.4 F < RSWT 102.9 F):
  `BufferNeedsCharge: Initializing -> HpOn`, CloseRelay to relay 6.
- 12:28:45 eGauge `03-hp-odu` ramps 104 → 476 → 770 W; ~820 W by 12:29:18.
- 12:29:30 Snapshot: `hp-odu-pwr` 788 W, `hp-lwt` 19.3 C (from 15.2),
  buffer-depth1 62.4 F (from 61.4); valve still 0.00 / 4.29.
- 12:31:53 House cold (zone1 ≥ 1 F under setpoint) and buffer empty for
  5 minutes: `Top State SystemCold: Normal -> UsingNonElectricBackup`,
  `GoDormant: HpOn -> Dormant`; relay 5 → TankAquastat, relay 8 → Boiler.
  Heat pump off after ~3 minutes at ~800 W.
- 12:37 eGauge: `03-hp-odu` 54 W, `05-oil-boiler` 0 W with zone 1 calling
  (`09-zone-1-white` 149 W). Neither source is heating.
- 12:38:15 Restarted with `SCADA_OIL_BOILER_BACKUP=False`. 12:39:25
  `Initializing -> HpOn`. First cold tick 12:41:25 (zone1-living-rm).
- 12:46:25 Five ticks later: `Top State SystemCold: Normal ->
  UsingNonElectricBackup`, `GoDormant: HpOn -> Dormant`, and backup sends
  CloseRelay to relay 6, so the heat pump stays on. eGauge `03-hp-odu`
  900 W at 12:46:42, 1088 W at 12:47:54; buffer-depth1 61.4 → 66.8 F;
  `hp-lwt` 15.2 → 20.7 C.
- 13:26:26 Relay 6 opened (buffer-depth1 103.2 F vs RSWT 102.9 F);
  13:29:26 closed again; heat pump drawing power 13:33:11.
- 14:58:54 Box layout swapped back to
  `hardware-layout.2026-09-20-pre-no-sieg-loop.json` (`UseSiegLoop: True`,
  the file maple ran April → noon today; the no-sieg layout kept as
  `hardware-layout.2026-09-20-pre-sieg-loop-on.json`) and scada restarted.
- 14:58:59 SiegLoop `Initializing -> Blind`, 110 s drive toward full send.
  One `Value error`: `auto.lc.n` is not the immediate boss of
  `auto.lc.n.sieg-loop.relay14`.
- 15:00:04 Local control sends `TurnOff` to HpBoss; relay 6 opened;
  SiegLoop receives `HpOff`. 15:01:04 local control `HpOff`.
- 15:02:59 SiegLoop `Blind -> HpOff`, "Moving to full keep position";
  relay 15 → 1, relay 14 → 0 (moving).
- 15:04:24 `sieg-flow` 5.11 gpm, `sieg-send` 0.02. 15:04:49 movement
  complete, relay 14 → 1.

## Analysis notes

- Flow channels are gpm × 100. Relay channels: 1 = energized. Relay 14
  energized = valve dormant; relay 15 de-energized = SendMore.
- Snapshots reach the local broker only while an admin is connected.
- Readings are async (report on change), so a large age on a steady value is
  not staleness by itself; `sieg-flow` jittered 498–502 while at full keep.
- The laptop clock runs ~1 min ahead of the boxes; times above are the
  box's.

## Notes for jm/spruce-unlimbo

Questions this window raised for the branch maple moves to. `main` stays as
it is.

- **How SiegLoop decides the heat pump is off.** It takes HpBoss's commanded
  state (`sieg_loop.py:403`); measured power enters only through the Blind
  test. The preference is to decide off from `hp-odu-pwr` under a
  threshold, so the valve follows what the heat pump did, not what it was
  told. Finding 12 gives the timings at maple: 4 s from relay 6 to under
  100 W, 3 min 45 s from relay 6 to drawing power again.
- **Blind means blind.** Today a heat pump that still draws more than
  500 W two minutes after being turned off makes SiegLoop `Blind`, and
  Blind drives the valve to full send, the position that de-stratifies the
  buffer. The scada is not blind in that case; the heat pump is not doing
  what it was told. State names carry their natural meaning: `Blind` is
  for missing data only, and a heat pump that ignores a command gets its
  own name and its own action. Once off is decided from power this case
  is simply "on".
- **Operational params for the two jobs of the loop.** Closing the loop
  when the heat pump is off (stops de-stratification) is wanted at every
  house with a sieg valve. The PID blend while the heat pump runs is a
  separate choice. The params need to switch the PID on and off on top of
  the off-closes-the-loop behaviour, without a layout regeneration.
- **Defrost.** The loop needs a decision for defrost: power drops and lift
  goes negative while the heat pump is still on. Not yet observed at maple.
- **SiegLoop after a restart.** Finding 15: four minutes `Blind` at full
  send, a first move that assumes the valve is at full keep, and a valve
  state that reads `SteadyBlend` at full keep. A restart with the heat
  pump off should reach full keep promptly, and the valve state should
  name where the valve is.
- **The admin panel moves the sieg relays.** With `UseSiegLoop: True`
  relays 14 and 15 report to the `sieg-loop` node, so their handles under
  admin are `admin.sieg-loop.relay14/15`. The panel sends to
  `admin.relay14/15` and the scada rejects it as not the immediate boss
  (finding 4). The only way to move the valve by hand today is a layout
  without the SiegLoop. Either the panel learns the handle a relay has in
  the current command tree, or an admin takeover puts every relay directly
  under admin. The same boss rule bites local control: at the 14:58:59
  restart `auto.lc.n` sent to `auto.lc.n.sieg-loop.relay14` and got
  "FromHandle auto.lc.n must be immediate boss of ToHandle".
- **Confirm at the next maple window: one folded full report per
  command.** From `7c3b5531` and `e4bd4b77` every command node folds
  its relays' full reports into its own, under the command's TriggerId,
  and a relay whose commander does not fold (admin, local control)
  reports to the scada. A dev run on a sim layout comes first; this is
  the real-board check. Read, from the scada log and the journal's
  `Report.FsmReportList`, one report per TriggerId and no report
  addressed to the panel:
  1. Each valve move, automatic or admin's `MoveSiegValve`: one report
     from `sieg-loop` whose atomics name `hp-loop-keep-send-relay`,
     `hp-loop-on-off-relay` (twice) and `sieg-loop` last; under admin
     the TriggerId is the panel's.
  2. Admin `TurnOff` / `TurnOn` through hp-boss: one report from
     `hp-boss` with its own `HpBossState` atomic(s) then
     `hp-scada-ops-relay`'s two; under `StratProtect` the TurnOn report
     arrives only after `SiegLoopReady`, with `PreparingToTurnOn` and
     `HpOn` atomics.
  3. A relay the panel commands directly (any `admin.<relay>`): its
     report appears in the journal under the panel's TriggerId.
  4. No `relay_nack` or `relay_silent` glitch on any node across the
     window; the boot's `hp-boss` report under a minted id shows the
     call relay opening.
  5. The motor clock: each `sieg-view` "Motor stopped" line's run time
     matches the commanded travel, not that plus the report wait.
- **Local-control state matches reality.** Decided: this changes on the
  branch. Finding 11: with no oil boiler, SystemCold leaves `HpOn` for
  `Dormant` and the backup node turns the heat pump on, so the reported
  state says dormant while the heat pump runs. Goes with the open question under "The 5-minute SystemCold
  mark": whether SystemCold should hold off while the heat pump is on and
  the buffer is rising.

## Folder contents & experimental method

All observations here were GENERATED during the session by watching the
running plant: admin snapshots from maple's local mosquitto, and the box
journal (`journalctl -u gwspaceheat`). Finding 2 is a journal DB query
(`gridworks.readings`, channel `primary-pump-pwr`,
`d1a1efdf-fb78-449a-8b10-390266dc9375`), re-pullable by anyone. Relay and
pump actions were taken by hand through the admin panel.

- `maple_flow_watch.sh` — one line per admin snapshot: flows, relays 14/15/
  11/12/vdc/6, powers, loop temperatures. Broker creds are read from the
  box `.env` inside the ssh shell and never printed. Appends to
  `snapshots.log` here.

```
./maple_flow_watch.sh        # stream until ctrl-c
./maple_flow_watch.sh 1      # one snapshot
```

- `hw1.isone.me.versant.keene.maple.ta-gw.readings-000.json` — journal DB
  pull, 11:45 → 14:20 ET, the seven channels findings 11–13 rest on:
  `hp-odu-pwr`, `hp-idu-pwr`, `hp-scada-ops-relay6`, `hp-failsafe-relay5`,
  `aquastat-ctrl-relay8`, `buffer-depth1` and `sieg-send`, decoded through
  maple's `layout.lite` 011 emitted 12:38. `sieg-send` reports about once a
  second, so it is kept for 13:20 → 13:45, the span finding 12 uses; the
  other six cover the whole window. Re-pull the seven channels across the
  full window with:

```
uv run python pull_readings.py --ta hw1.isone.me.versant.keene.maple.ta \
    --channel hp-odu-pwr --channel hp-idu-pwr \
    --channel hp-scada-ops-relay6 --channel hp-failsafe-relay5 \
    --channel aquastat-ctrl-relay8 --channel buffer-depth1 \
    --channel sieg-send \
    --start '2026-09-20 11:45' --end '2026-09-20 14:20' \
    --out 2026-09-20-maple-starts-heating
```

- `defrost_hunt.py` — the defrost hunt and profile. `pull` fetches one
  gw.readings instance per ET day through `../pull_readings.py` (a week in
  one query runs into the journal DB's statement timeout); `hunt` decodes
  them through the snapshot codec and writes the two items below. The day
  instances stay in `<dir>`, outside the repo.
- `maple-defrost-events.json` — every stretch found, its kind and numbers,
  the rule's constants and the summary. Interior result with no word; the
  script's `DefrostEvent` names the word that would retire it.
- `defrost-signatures/` — five example defrosts, each a gw.readings
  instance of the hunt's six channels from 5 min before the lift goes
  nonpositive to 2 min after it recovers: the shortest, quartile, median
  and longest by time with lift at or below zero. The filename condition
  is `defrost.d<ET date>.t<ET start time>`. `hunt` writes the signatures
  of all 67 into `<dir>/defrost-signatures/`.

Every number in "Defrost profile" is in `maple-defrost-events.json`
(`Summary` for the statistics, `Events` for each stretch), and the two
commands below reproduce that file from the journal DB.

```
uv run python defrost_hunt.py pull --start 2026-03-26 --end 2026-05-16 --work <dir>
uv run python defrost_hunt.py hunt --work <dir>
```

No word covers a hand-run bring-up log or a derived plant event; the
readings instances and `instances/gw.experiment.run-000.json` are the sema
results.

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only — the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from <instance>.json
