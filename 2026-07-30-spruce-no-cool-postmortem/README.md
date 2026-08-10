# Spruce no-cool postmortem, 2026-07-29/30

> What this is: the working investigation of the spruce overnight
> no-cool (2026-07-29→30) and the daytime anomalies — issues with the
> gw108 and the Samsung's behavior around power/panel state. The raw
> data and pull scripts live beside this file; the logbook entry with the
> verdict is the index record. Field events live on the per-home issue
> (GRI-11).

**Preamble — the install session.** On 07-29 George was onsite installing
tank1 temp sensors and eGauge power metering on both mains and the HP ODU
(lines over the garage roof). The incident begins inside that session. Note
that the pi never power-cycled (continuous boot since
07-18, journald-verified), and the two services on it — the summer hack
and `gwspaceheat` — are apparently only ever stopped and started by a
person: every start/stop in the window is accounted for by work-session
actions or systemd reacting to a crash.

**The provoking event.** There is evidence that the heat pump went into a
"soft off" state sometime between 15:21 and 15:38 on 07-29, in which it
refused to listen to commands until the next morning, when the spruce owner turned it
on at the touchscreen (~09:15). In addition, the 0x21 i2c chip on the Gw108
began exhibiting worse behavior around that time. A second puzzle appeared
the next morning: a distinct **~17 W low-power state** on the heat pump's
feed (09:21–09:26; normal standby is 61–66 W), during which a
pin-verified closed call went unanswered. Details in the timeline.

**Zeroing in on the gw108 board.** Two i2c chips on the board are
suspect, with different histories and different fates:

- **dac3 (MCP4728 DAC behind mux channel 3 — the secondary pump's 0-10V
  speed signal).** Before this day: reliable since the 07-15 deployment —
  written at every state change and re-asserted every 5-min enforce pass,
  no errors. What happened: first symptom 03:10:38 on 07-30 — one write
  raised EIO (Errno 5, Input/output error); the hack had no try/except
  on that path, so the single failed write killed the whole process.
  The chip then recovered and served the morning's restarts;
  at 11:25:16 a write died mid-transaction, and the chip has never ACKed
  since — its i2c interface is dead while its analog output stage still
  holds the last commanded 7.55 V. Its two sibling DACs (mux channels 1
  and 2) answer normally.
- **The 0x21 TCA9555 expander — the chip carrying ALL THREE cooling
  actuators (hp-call, secondary-pump relay, iso valve).** Before this
  day: occasional spontaneous mid-run brownouts — four known events on
  07-16/17, irregular, hours apart, which is what got the auto-repair
  built. What happened: starting 15:33 on 07-29 (mid-install-session)
  its behavior changed shape — it now browns out within seconds of EVERY
  service start (detected at each start's first 5-minute enforce pass,
  register snapshots showing the chip's power-on state), while running
  clean for hours between starts. A brownout floats its pins, dropping
  all three cooling actuators at once (safe-off direction). The sibling
  expander at 0x20 (zone holds), same chip type on the same board, has
  never once reset — the weakness is local to 0x21's corner, not
  board-wide.

**Conclusions (tentative, gw108).** The two chip failures look like one
electrical illness in one board corner, degrading in stages, rather
than two coincidences: dac3's i2c interface is dead outright (output
stage alive, siblings healthy — chip-level damage, whether from a
supply transient or an independent cause); the 0x21 expander's
brownouts went from occasional-and-spontaneous (July) to
reliably-triggered-by-service-start in the install-session window, and
the start sequence's distinctive act is DAC/mux traffic — probing the
sick corner appears to be what knocks the expander over. The sibling
0x20 expander has never reset, so the weakness is local, not
board-wide. The supply/decoupling theory is the leading candidate: the 0x21
corner's 3.3 V (fed solely from the pi's rail) lacks local buffering, so
current spikes from relay/bus/DAC activity momentarily sag the chip's
supply below its power-on-reset threshold — the planned rework is bulk
decoupling capacitance at board position U18 plus an improved ground
return (2026-07-18). None of this is yet confirmed by electrical measurement.

**Needs further testing.**

- What was the ~17 W low-power state (09:21–09:26 on the Emporia HP
  feed; normal standby 61–66 W)? Candidates: the spruce owner pressing
  power off/on, or an internal post-run state. Ask first; if
  unresolved, it should reproduce at the panel with the Emporia
  watching.
- What turned the heat pump soft-OFF between ~15:21 and ~15:39? The
  cooling stop itself was commanded (service stopped 15:17:24 → normal
  stand-down); the leading theory for what followed is breaker work on
  the HP circuits for the CT install (ask George — he will likely know;
  not site-wide, the pi never blinked). The testable half: what happens
  to the heat pump's state when it is power-cycled? The 07-16
  observation (came back soft-OFF, ignoring the external contact) is a
  single datum and the load-bearing assumption behind the breaker
  theory — worth a deliberate witnessed test: cut the control-box
  breaker, restore, observe panel state and contact responsiveness.

## Timeline


- **07-29 14:00 → ~15:21 — the last cooling run.** Primary flow up to
  7.65 GPM settling ~2.5 GPM; hp-lwt pulled 62.6 → 50.2 °F. Last nonzero
  flow reading 15:01:44 (2.54 GPM); first zero report 15:22:20 — the stop
  moment is explained by the 15:17:24 entry below (commanded stand-down
  ≈15:21).
- **07-29 15:17:24** — the summer hack exits (work-session context; the
  log line is its exit handler, which runs identically on a deliberate
  stop or a crash). The exit handler's failsafe opens **the cool call**
  — the gw108 relay (0x21 reg2 bit0) de-energizes the RIB coil, whose
  normally-open contact stops bridging Samsung B20→B21, the
  Thermostat-1 cooling input — so a dead controller never leaves the
  heat pump commanded on. The heat pump stands down on its normal
  ~4-min delay (≈15:21, matching the first zero-flow report 15:22:20).
  **The cooling stop was commanded, not a fault — and the stand-down
  itself is the heat pump's last observed RESPONSE to the contact.**
  The call was then re-closed in three windows (15:33–15:38 nominally,
  though the chip reset floated the pins for most of it; 15:38–15:53
  post-repair; 15:53–16:00) — zero primary flow in all three. (The
  15:38:15 register snapshot shows cfg=all-1s — the chip-POR signature;
  a `gw108_test_code` run writes zeros and cannot produce it, so that
  reset was a genuine 0x21 brownout, whether or not test-code sessions
  also happened that afternoon.)
- **The heat pump went soft-OFF between ~15:21 and ~15:38.** "Soft-OFF"
  (previously "panel-OFF") = the OFF state on the heat pump's control
  box touchscreen, in which it ignores the external contact entirely
  (the 07-16 lesson). INFERRED, strongly: it ignored physically-verified
  closed calls in the latter two windows and all night, and the panel
  power button is a toggle — the heat pump starting immediately on
  the spruce owner's 09:15 press means that press was OFF→ON, so it had been OFF.
  HOW it became OFF is only hypothesis: a power interruption to the
  control box (breaker work for the CT install; the known 07-16
  behavior — control-box power loss ⇒ comes back soft-OFF) or a human
  pressing the panel button that afternoon. Both fit the data; George's
  account of the session discriminates.
- **07-29 afternoon service starts** (work-session stop/starts): 15:33
  start → 0x21 reset detected 15:38:15 — **the reset-on-every-start
  pattern begins here**, mid-install-session. 15:53 start ran only 12 min
  (exited 16:05) with its enforce pass finding the config registers clean;
  17:23:54 start → reset 17:28:58; every subsequent start resets.
- **07-29 15:22 → 07-30 09:15 — ZERO primary flow in every reading**: the
  primary pump (in the ctrl box; the direct is-the-heat-pump-on observable)
  never ran overnight.
- **07-29 15:00–16:00** — secondary flow in fragments (7.7 → 0 → ~5 →
  1.3 GPM): the last run's tail plus the work-session service restarts;
  zero 16:15 → 19:45 (the on-peak OFF posture).
- **07-29 20:00:33** — TOU ON. The gw108 did everything expected,
  verified at the pins (iso open, pump relay closed, hp-call closed;
  DAC speed signal 7.55 V), and held it green every 5-min enforce pass
  through the night. **The secondary pump demonstrably turned on**
  (~7.5 GPM — its whole chain pin → relay → power → water proven
  physically). **The primary pump did not turn on** (zero flow): the
  Samsung never acted on the closed call. (The 20:00 primary-flow
  bucket's 0.67 GPM max blip coincides with the secondary pump starting —
  induced parasitic flow or meter noise.)
- **07-29 20:00 → 07-30 07:00 — the secondary pump ran ALL NIGHT at
  ~7.5 GPM** with sec-lwt ≈ sec-ewt throughout (zero split: no heat
  exchange — the primary side was dark). The loop stirred and slowly
  warmed 58 → 63 °F (envelope gains + the pump's own heat), circulating
  warm water through the HX to nowhere.
- **07-30 03:10:38 → 03:15:54 — ~5 minutes of trouble: a CONFLUENCE of
  both chip problems, in three phases.**
  - *Phase 1 (03:10:38 → 03:10:49, dac3's illness):* the hack's routine
    enforce-pass DAC re-assert — one i2c write to dac3 — dies
    mid-transaction (OSError Errno 5, EIO; dac3's first-ever symptom).
    No try/except on that path, so the single failed write kills the
    whole process; the exit failsafe deliberately opens the call and
    pump relay. 11 seconds of commanded-off.
  - *Phase 2 (03:10:49 → 03:15:54, 0x21's illness):* systemd restarts
    the hack; the start sequence commands HP ON (03:10:53) — but this
    start, like every start since 15:33, browns out the 0x21 expander.
    Pins float: for ~5 minutes the log says call/pump/iso are set while
    nothing is physically driven. The window is invisible to the
    software because readback comes from the chip's flip-flops, which
    the brownout also reset — only the config registers betray it.
  - *Phase 3 (03:15:54):* the first 5-minute enforce pass reads the
    config registers, sees the POR signature, logs the CRITICAL with
    register snapshot, re-initializes, re-asserts — trouble over. The
    semantic check's secondary-flow = 0 at the same pass was REAL and
    corroborates: the 03:00–03:30 flow buckets dip to 4.2/5.9 GPM
    average (pump off ~5½ min across phases 1–2), back to 7.48 by
    03:30. The ~5-minute bound is the enforce CADENCE, not the fault
    duration — the same fault with a faster check would have been a
    faster repair.
- **03:16 → 07:00** — call closed, enforce green throughout.
- **07:00:25** — TOU OFF per schedule; pump relay opens 07:00:29.
  **RESOLVED:** the 07:05:29 semantic CRITICAL (flow=748 with pump
  commanded OFF) was a false positive from a **secondary-BTU pico
  dropout**: all four of its channels went silent 06:55:00 → 07:07:51
  (~13 min, spanning the pump-off; pump-ct normally chatters every
  30–60 s). The scada's snapshots kept broadcasting the stale flowing
  value, which the check trusted. No pico-cycler action in the scada
  journal for the window — the dropout was the pico's own (wifi or
  self-reset), the longest of the night's intermittent staleness
  episodes (semantic checks also skipped stale at 01:25, 03:00, 06:35).
  Design note: the flow check needs a per-reading timestamp guard, not
  just snapshot freshness.
- **Incident-window data gap:** the deployed scada rejected the
  replacement tank1 pico all through 07-30 (`pico_9a7935 - not
  recognized!` every minute — the field swap predated the layout carrying
  the new uid, fixed by the 2026-08-03 layout deploy). tank1/store temps
  are absent for the incident window.
- **Overnight outcome** (George, eGauge): the HP never ran.
- **08:35:04** — manual call ON (hack stopped; pins 1/1/1). Window lasted
  ~90 s (hack restart 08:36:38 re-asserted the on-peak OFF).
- **09:13:18** — manual call ON again (pins 1/1/1). No eGauge response.
- **~09:15** — the spruce owner presses the panel power button: the primary pump
  starts at 09:15:32 (ramp to 7.55 GPM in 2 s) against the standing
  call. (Proves: the heat pump was soft-OFF until then, and the call path was
  conducting to the Samsung terminals at that moment.)
- **09:17:35** — call opened manually; hack restarted 09:17:38 (OFF).
  Emporia: compressor ramps down 09:19 (667 W), stopped by 09:20 —
  ~2.5 min response to the call opening; primary pump stops 09:20:12.
- **09:21 → 09:26 — the heat pump's feed drops to ~17 W** (Emporia Mains A+B —
  the CTs are on the HP/compressor feed, not house mains; normal ODU
  standby is 61–66 W on this measure): a distinct low-power state,
  identity open (the spruce owner pressing power off/on? an internal post-run
  state?). Standby returns 09:26–27. Not `hp-ctrl-box-pwr` — the ctrl
  box (display + primary pump) is a separate feed, and its analytics
  channel has never reported.
- **09:22:43** — start-reset detected + repaired (hack running).
- **09:24:43** — hack stopped; manual call ON (pins re-verified 1/1/1 at
  09:27:40, expander healthy). **The call landed inside the 17 W
  low-power window.** Zero primary flow and no draw step for the entire
  standing call (opened 09:31:17 by the hack restart — held 6.5 min,
  of which only ~4.5 min after standby returned).
- **09:31:17** — hack restarted (call opened per on-peak).
- **11:10:10 → 11:25:16** — hack run: two clean enforce passes (11:15,
  11:20 — dac3 writes succeed), then **11:25:16 dac3 write EIO → process
  crash**. From 11:25:27, dac3 never ACKs again (Errno 121, then EIO on
  probes). systemd crash-loops the service ×863 (import dies at the dac3
  probe).
- **~13:05** — interactive `gw108_test_code` import fails on the same
  dac3 probe; the partial import clears both expanders (zone holds
  wiped).
- **13:09–13:10** — `hp_on.py` (JM): call CLOSED, pins 1/1/1.
  **RESOLVED (Emporia): the call WORKED** — draw steps at 13:10 (347 W),
  compressor at 1620 W by 13:13. The heat pump responds to a closed call
  from normal standby in ~1 minute. (The primary pico's 23.6-min
  reporting gap, 13:00:00 → 13:23:34, hid the flow — its 13:23:34
  report was mid-run resumption, not a start. Outside its gaps the pico
  reported ~5-min zeros, so the 09:20 → 13:00 zero-flow stretch IS
  verified.)
- **13:23:19** — iso/pump/call re-asserted: irrelevant — the heat pump had
  been running since ~13:10. 13:23:45 hack start attempt resumes the
  crash-loop.
- **13:31–13:42 — the spruce owner changes the heat pump over to SCHEDULE mode** (on a
  phone call with George). Emporia: the running heat pump ramps down
  13:33–35 (~110 W), then relaunches 13:36 climbing to ~2400–2650 W by
  13:40+ — a harder restart in the new mode. The 13:36:11 primary-flow
  blip (~26 s to zero) is the changeover's pump interruption.
- **13:35:45** — crash-loop stopped. The service has been inactive since.
- **13:36** — zone holds re-asserted manually (held since).
- **07-31 → 08-03** — call standing CLOSED (nothing to open it); the
  heat pump runs **its own internal schedule** (the 13:31–42 changeover)
  through all TOU windows. **The secondary pump runs CONTINUOUSLY at
  the full 65 % setting the whole tail** — every flow reading 7.35–8.12
  GPM (n=1,455, none lower), pump-ct pinned 1.67–1.71 V: the relay
  latched closed since 13:23 07-30 and dac3's volatile 7.55 V output
  still holding despite its dead i2c interface. 08-03: mux healthy,
  DACs on ch1/ch2 ACK, **dac3 still dead** (EIO).

## Analysis notes (reading key, data quality)

**Reading key for the timeline.** Baseline 07-26→28: primary flow
> 1 GPM ⇔ active cooling (lwt ≈ 46 °F, ewt−lwt ≈ +4.7 °F); flow ≈ 0 ⇔
idle (lwt drifting to ≈ 54 °F, split collapsed). That two-state
signature is what makes `primary-flow` the is-the-heat-pump-cooling
discriminator used throughout.

**Diagnostic muddiness.** Two gaps make the record harder to read than
it should be: the secondary-BTU pico cuts out a fair amount (its
dropouts manufactured one false CRITICAL and hid one real heat-pump
start — the 2026-08-03 pico-gap-analysis has the fleet statistics), and
the power metering wasn't all in place — the hp-ctrl-box-pwr and
hp-odu-pwr channels entered the layout only with the 08-03 deploy, so
no reports carried them during the incident (verified against the S3
eventstore). The Emporia minutely data on the heat-pump feed fills much
of this in.

## Folder contents & experimental method

**How the data was obtained:** entirely from immutable stores — the
`gw.readings` instance is a pull of what the deployed scada reported
during the incident window (journal database; anyone can re-pull it),
and the Emporia CSV is an external download (see its provenance
header). This is a `-postmortem`: nothing was generated and the running
system was never touched.

**Files in this folder.**

- `emporia-7408E4-spruce-hp-feed-1min.csv` — EXTERNAL EVIDENCE, kept
  committed because it is not regenerable from GridWorks systems:
  Emporia 1-minute data on the HP feed, downloaded by George from the
  Emporia portal (provenance header in the file; the two mains-CT
  columns sum to the compressor-side draw).
- `instances/` — sema-typed results, constructed through the vendored
  snapshot and derived entirely from this folder's `gw.readings`
  instance (regenerate with `emit_instances.py`): the analysis window
  as `gw.experiment.run`, and per-zone `gw.channel.jump.stats` over
  the window (the incident's electrical spike cluster,
  machine-readable: zone3 40 spikes, zone4 36, max 126 mV).
- `hw1.isone.me.versant.keene.spruce.ta-gw.readings-000.json` — the
  incident window's raw readings as one validated `gw.readings`
  instance: the channel words (from the scada's own layout.lite
  emission in the eventstore, 07-30) together with 284,922 readings
  across 29 channels — this file is the window's data; CSV views of it
  are generated on demand, never committed (see the paragraph at the
  bottom). Produced by the repo-top `pull_readings.py` (three-stage:
  eventstore channel words → DB values → assembly).
- `emit_instances.py` — derives the folder's result instances from the
  `gw.readings` instance (see above).

The window's data reproduces from scratch with the repo-top
`pull_readings.py`:
`../pull_readings.py --ta hw1.isone.me.versant.keene.spruce.ta
--like 'buffer%' --channel hp-lwt --channel hp-ewt
--channel secondary-lwt --channel secondary-ewt
--channel secondary-flow --channel primary-flow --like '%heat-call'
--like '%opto-input' --like 'zone%gw-temp' --like 'zone%gw-microvolts'
--start '2026-07-26 00:00' --end '2026-08-03 00:00' --out .`

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only — the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from \
        hw1.isone.me.versant.keene.spruce.ta-gw.readings-000.json

**Display CSV of the jump stats** (one row per zone, thresholds and
jumps in mV; from the repo top):

    uv run python stats_display.py 2026-07-30-spruce-no-cool-postmortem/instances/*-gw.channel.jump.stats-000.json
