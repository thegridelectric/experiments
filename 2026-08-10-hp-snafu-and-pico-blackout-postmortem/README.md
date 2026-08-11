# hp-snafu-and-pico-blackout-postmortem, 2026-08-10

> What this is: the investigation of the spruce evening incident of
> 2026-08-10 — the heat pump ignored the 20:00 cool call, and the
> GridWorks wifi went off the air at 5:04 pm leaving every pico zombie
> — with the evidence collected as sema instances and frozen captures.
> The incident issue is OPS-492; the logbook entry is the index record;
> field history lives on GRI-11.

**Are the two events related? Probably not through our board.** The
gw108's telemetry was clean through both — ADS canary zero jumps all
day (the canary that flagged the July illness three days early), zero
i2c errors, pin-level readback green every 5 minutes — and its one
misbehavior, the 15:09 service-start brownout, was caught,
auto-repaired, and precedes both events. The heat pump's fault sits in
the Samsung's own control state (or, less likely, the wiring beyond
our pins); the pico blackout sits in the house router's radio. Their
shared afternoon is the only link, and it is unexplained.

## Impact

From 20:00 the TOU schedule commanded cooling into standing zone calls
(zones 3 and 5) and no cooling was delivered; rooms drifted to
72–73.5 °F by 22:20, uncomfortable but not runaway. From 17:04 ET the
house lost all pico telemetry (flow, tank depth, lwt/ewt), blinding
flow verification. The wifi-herd observation window that began with
the 13:45 deploy is contaminated from 17:04 on.

## What went well

The summer hack caught the day's one board misbehavior — the 0x21
brownout at the 15:04 service start — at its first enforce pass,
auto-repaired it, and physically landed the afternoon's call; from
then on its pin-level readback verified the commanded posture every
5 minutes with no further CRITICALs. The pico-cycler noticed the first
flatline within a minute, ran its full VDC rescue per pico, declared
each zombie honestly, and kept the hourly roster firing. The wired
observability plane (scada, eGauge, zone ADS temps, opto stat calls)
stayed intact throughout, which is what made remote diagnosis possible.

## The heat pump — and how we know

**What happened:** the unit did not follow the gw108's instruction to
turn on at 8 pm, despite a physically verified closed call. The
question under triage: is this the heat pump (in one of two ways), or
the scada signal?

**The afternoon proves the whole command chain worked.** Times from
the hack journal, response from the eGauge readings:

- 15:02:52 — service stopped, contact opened: compressor fell
  792 → 29 W in ~4 s.
- 15:04:04 — service restarted, call commanded closed — but the 0x21
  expander had browned out at service start (pins floating), so
  nothing physically closed and the unit correctly did nothing.
- 15:09:04 — the enforce pass caught the reset (CRITICAL),
  auto-repaired, re-asserted the call: pump answered at 15:09:12,
  compressor ramping from 15:09:22.

So as of 15:09: FSV 2091=1 authority real, unit ON at the panel, the
whole hack → 0x21 → relay → RIB → B20/B21 chain working in both
directions, response time in seconds.

**Then 16:00 looks like the schedule acting.** The unit began ramping
down at or before ~16:00:03–:04 and read 21 W (off) by 16:00:05 — but
the contact stayed closed until 16:00:07.161. One clock: the readings'
timestamps are ScadaReadTimeUnixMs, stamped by the same pi that stamps
the hack journal, and the meter's ~1 s averaging plus poll cadence
make real events earlier than their timestamps, never later — the lead
can only widen. Under the documented 2091=1 semantics (the Drive doc
"PRIMARY — Samsung AE055 control interface": the contact is the SOLE
compressor authority, panel passive), the unit should not have stood
down while the contact was closed.

**The evening rest looked healthy, then 8 pm failed.** Between 16:00
and 20:00 the ODU rested exactly like a healthy off-peak evening
(~12 W low 16:00–18:00, ~60 W standby 18:00–19:00, ~12 W 19:00–20:00,
control box 4–6 W throughout — the week's baseline is in the
hp.baseline instance). Then:

- 19:57:55–:57 — ODU rises 42 → 94 → 50 W and settles at ~60 W: the
  unit wakes itself to normal standby two minutes before 8, on its
  internal schedule's timing, before our call exists.
- 20:00:14 — the hack closes the cool call into the RIB; pin-level
  readback verifies it, and re-verifies every 5 minutes all evening.
- Then nothing. On every healthy night this week, 20:00 sharp means
  control box to ~100 W (primary pump) within seconds and compressor
  ramping to 1.7–2.9 kW. Tonight the control box never left 4–6 W and
  the ODU never exceeded 94 W — 90 minutes of standby holding a
  verified cool call.
- 21:30:47 — ODU steps back to ~12 W low-power and stays there, call
  still closed.

**What we suspect.** The heat pump in one of two ways, or the scada
signal:

1. *The HP's run state has faulted* — the 07-29 pattern, where the
   unit went deaf to commands until Matt pressed ON at the
   touchscreen. Settings right, state wrong; fixed by a state reset;
   can recur.
2. *The HP's settings aren't what we think* — the FSV session's end
   state differs from intent. Simple non-save is nearly ruled out
   (the contact demonstrably had authority at 15:02–15:09), but a
   half-applied 2091 — took hold in RAM, lost authority at the 16:00
   schedule re-arbitration, stable only after a power cycle — fits
   the whole day and cannot be ruled out from the FSV screens, which
   show the SAVED value, not the EFFECTIVE one.
3. *The scada signal, physically* — a break downstream of the
   expander pin (relay contacts, RIB, B20/B21 wire — the stretch
   pin-readback cannot see). Requires spontaneous failure of a chain
   proven at 15:09 with nobody onsite; nothing correlates except the
   unexplained 17:04 house event.

The gw108 board's logic and power are not on the list — see the note
at the top.

## The wifi blackout — and how we know

**What happened:** at 5:04 pm the GridWorks wifi went off the air.
Every wifi client dropped in the same minute — all six layout picos,
plus the spruce pi's own wifi interface. The pis are fine on ethernet,
and the router is still up on the wired side, but the GridWorks SSID
has not been broadcast since, on either band, so none of the picos can
come back. VDC power-cycles cannot rescue a pico from an AP that is
not broadcasting; the zombie declarations are real but the picos are
probably healthy.

**How we know:**

- The spruce pi's wlan0 held an association to the GridWorks SSID and
  lost it at 17:04:29 — NetworkManager logged `ssid-not-found`
  (`evidence/pi-journal-networkmanager.log`); its kernel began failing
  wifi channel operations at 17:04:18 and hasn't stopped
  (`evidence/pi-journal-brcmfmac.log`). Nothing pico-side can explain
  the pi's independent radio losing the same network.
- The last pico posts landed 16:59:59–17:00:00; the six zombie
  declarations follow 17:07–17:21 (`instances/pico.blackout/`). The
  :00-flat timestamps are a cadence artifact — pico code reports on
  the minute when the value is unchanged — so the readings alone bound
  death to 17:00–17:05, and the pi's wifi log pins it at ~17:04.
- The GridWorks SSID is served by the house router: the profile's
  last-seen BSSID (62:7F:F0:3B:2C:27) is the same MAC family as the
  router's wired MAC (68:7F:F0:3B:2C:24). The router still answers on
  ethernet and beacons a hidden 5 GHz BSSID, but nothing on 2.4 GHz,
  while neighboring 2.4 GHz networks scan strong
  (`evidence/pi-wifi-state.txt`). Pico W radios are 2.4 GHz-only.
- Every wired device stayed healthy: pi, router, eGauge, and all
  eGauge- and board-fed channels (the readings instances in this
  folder). Every wifi device died in the same minute.

**The 5 VDC bus is exonerated for this incident.** Per the Gw108 RevC
schematic (`gridworks-hardware/PCBs/KiCad/FullScada1/Gw108_RevC/
external_5v.kicad_sch`), the pico bus is the board's global +5V rail
switched through relay K3 out to the J17 terminals — shared with the
board's logic, including the corner under supply suspicion since July
(U18, a TCA9555). A rail sag could in principle reach the picos, but
tonight's failure is observable in the air from the pi's own radio,
which no VDC-bus state can cause. Standing check: if the SSID returns
and the picos still don't rejoin, the bus is the next suspect — and no
journaled channel currently reports the board's 5V current.

## Timeline (ET, 2026-08-10)

- 12:16 — pi reboots (previous continuous boot since 07-18).
- ~12:20–13:45 — site work session (zombie pattern: secondary-btu
  12:20; buffer/tank1/fancoil/floor1/pipes1 12:54–13:39). The hack
  service is down at noon, so the 12:00:05 pump start + compressor
  ramp is the Samsung's internal schedule. FSV 2091 → 1 set during
  this session; exact time TBD (George).
- 13:45 — herd-reduction deploy: fancoil, pipes1, floor1 picos
  disconnected and de-layouted.
- 15:02:52 — service stopped: contact opens, compressor 792 → 29 W in
  ~4 s (witnessed contact authority, unit ON).
- 15:03:59–15:04:04 — service start; call commanded closed but 0x21
  browned out at start (pins floating): no response, correctly.
- 15:09:04 — CRITICAL: expander reset detected at first enforce pass;
  auto-repair re-asserts all states. Pump 15:09:12, compressor ramp
  from 15:09:22 — the contact call lands.
- 16:00:00–:07 — unit stands down at least 3 s before the hack opens
  the contact at 16:00:07 (the sole-authority puzzle above).
- 16:59:59–17:00:00 — last posts from all six remaining picos.
- 17:04:18 — pi kernel: first wifi channel failures, continuous since.
- 17:04:29 — pi's wlan0 GridWorks association ends (`ssid-not-found`).
- 17:05:13 — pico-cycler detects the first flatline; VDC rescues begin.
- 17:07:23–17:20:48 — all six picos declared `pico-just-zombied` after
  three failed VDC cycles each.
- 18:00–22:00 — hourly `pico-zombies` roster, six picos standing.
- 19:57:55 — hp-odu-pwr rises to normal standby (internal-schedule
  timing).
- 20:00:10–:14 — hack commands HP ON; call closed and pin-verified;
  enforce green every 5 min through the evening.
- 20:00 onward — zones 3 and 5 calling; control box stays 4–6 W, no
  compressor.
- 21:30:47 — ODU drops to ~12 W low-power, call still closed.
- ~22:10–23:45 — remote diagnosis; these captures and pulls.

## Analysis notes

- hp-odu-pwr baselines (07-30 postmortem + this folder's hp.baseline
  pull): ~61–66 W normal standby; ~12–17 W distinct low-power rest;
  1.7–2.9 kW compressor. The Samsung's internal schedule mirrors the
  TOU windows (on 12–16 and 20–07 weekdays).
- The hp.baseline pull has two multi-day journal holes (08-03 15:30 →
  08-05 15:30, and Sat 07:00 → Mon 07:00); the baseline rests on
  08-05 evening through 08-08 morning plus 08-10 morning. The S3
  eventstore could fill the weekend if ever needed.
- The pico.blackout pull spans the 13:45 de-layout: fancoil-/pipes1-/
  floor1- channels appear only before 13:45 (declared-then-absent per
  the layout current at window end) — not dropouts.
- Hidden SSIDs do not broadcast names: the GridWorks-SSID
  identification rests on the BSSID MAC family plus the pi's
  NetworkManager profile, not on a scan hit for the name.
- The scan and ping captures in `evidence/` are point-in-time incident
  state, frozen (collect_pi_evidence.sh refuses to overwrite).

## Folder contents & experimental method

All readings and glitch data come from the immutable store (journal
DB, re-pullable by anyone with DB access); the `evidence/` files are
EXTERNAL EVIDENCE captured read-only over ssh from the spruce pi
during the incident. Nothing touched the running system: no service
stopped, no relay commanded, no router configuration changed.

- `hw1.…spruce.ta-pico.blackout-gw.readings-000.json` — 27 pico- and
  board-fed channels (flow / depth / lwt / ewt / micro-v / pump-ct),
  12:00–22:30 ET: the blackout cutoff and the surviving board
  channels side by side.
- `hw1.…spruce.ta-hp.norun-gw.readings-000.json` — hp-odu-pwr,
  hp-ctrl-box-pwr, dist-pump-pwr and the zone heat-call channels,
  15:00–22:30 ET: the witnessed afternoon test and the evening
  no-run.
- `hw1.…spruce.ta-hp.baseline-gw.readings-000.json` — the same
  channels 08-03 → 08-10 13:00: the healthy-week power baseline.
- `instances/pico.blackout/<node>.<created-ms>-pico.blackout-glitch-000.json`
  — the 12 spruce glitches of the 16:00–23:00 window (6
  `pico-just-zombied`, 6 `pico-zombies` rosters), decoded through the
  vendored `glitch` word and re-emitted verbatim.
- `archive_glitches.py` — the glitch puller/archiver.
- `hp_power_analysis.py` — band-classified power timelines
  (low / standby / ACTIVE) from this folder's instances, no DB.
- `collect_pi_evidence.sh` — the pi-side capture script (ssh,
  read-only, refuses to overwrite existing captures).
- `evidence/pi-journal-pico-cycler.log` — the cycler's rescue
  sequence 16:55–17:25. EXTERNAL EVIDENCE (journald).
- `evidence/pi-journal-summer-hack-evening.log` — the 20:00
  transition and every enforce pass to 22:30. EXTERNAL EVIDENCE
  (journald).
- `evidence/pi-journal-networkmanager.log` — the 17:04:14 association
  drop and `ssid-not-found` failure. EXTERNAL EVIDENCE (journald).
- `evidence/pi-journal-brcmfmac.log` — first wifi-channel failures
  and their continuation. EXTERNAL EVIDENCE (journald).
- `evidence/pi-wifi-state.txt` — NetworkManager GridWorks profile,
  device status, wifi scan, neighbor table, ping sweep. EXTERNAL
  EVIDENCE (point-in-time).

Regenerate the store-backed data from scratch:

    uv run python ../pull_readings.py \
        --ta hw1.isone.me.versant.keene.spruce.ta \
        --like '%-flow%' --like '%-depth%' --like '%-lwt%' \
        --like '%-ewt%' --like '%micro-v%' --like '%-pump-ct%' \
        --start '2026-08-10 12:00' --end '2026-08-10 22:30' \
        --condition pico.blackout --out .

    uv run python ../pull_readings.py \
        --ta hw1.isone.me.versant.keene.spruce.ta \
        --channel hp-odu-pwr --channel hp-ctrl-box-pwr \
        --channel dist-pump-pwr --like 'zone%-heat-call' \
        --start '2026-08-10 15:00' --end '2026-08-10 22:30' \
        --condition hp.norun --out .

    uv run python ../pull_readings.py \
        --ta hw1.isone.me.versant.keene.spruce.ta \
        --channel hp-odu-pwr --channel hp-ctrl-box-pwr \
        --channel dist-pump-pwr --like 'zone%-heat-call' \
        --start '2026-08-03 00:00' --end '2026-08-10 13:00' \
        --condition hp.baseline --out .

    uv run python archive_glitches.py

Analysis and display views:

    uv run python hp_power_analysis.py

    uv run python ../pull_readings.py --display-from \
        hw1.isone.me.versant.keene.spruce.ta-hp.norun-gw.readings-000.json

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
files are the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
siblings are presentation only — the same readings as natural-unit
floats, converted per each channel word's own encoding. Regenerate any
time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from \
        hw1.isone.me.versant.keene.spruce.ta-pico.blackout-gw.readings-000.json

## NEXT STEPS

Heat pump visit (Matt or Bradley; coordinate with Jessica first so
the cool call is held closed during the test):

1. BEFORE touching anything: photograph the main screen, the
   schedule screen, and every FSV screen — especially 2091.
2. Press ON at the panel with the call closed.
   If the compressor starts within seconds: run-state fault
   confirmed (hypothesis 1). Stop here and report.
3. If it did not start: power cycle the unit at the breakers — BOTH
   circuits, MAIN POWER and HEATER POWER are separate.
   Turn the unit ON at the panel; "Thermostat connected" should show.
   Test the call in both directions (close → starts; open → stops).
   If this fixes it: hypothesis 2 confirmed — record "FSV authority
   changes need a power cycle to be stable" on GRI-11 and in the
   Drive PRIMARY doc.
4. If it still ignores the call: put the multimeter on the
   relay → RIB → B20/B21 chain.
   These are 230 V terminals — dead-work procedure: both breakers
   off, live-dead-live meter check before touching.
5. Write down the exact clock time of every action taken, so each
   can be matched against the eGauge power record afterward.

Router (anyone at the house, or the owner):

6. Power cycle the router.
7. After it boots, check for the `GridWorks` SSID (any phone's wifi
   list works). If it's back, the picos should resume posting within
   ~15 minutes on their own — no other action needed.
8. If the SSID does not return: log into the router UI at
   192.168.2.1 and re-enable the 2.4 GHz radio / re-create the
   `GridWorks` SSID with the existing passphrase.
9. Fallback if the router won't cooperate: any 2.4 GHz access point
   wired into the LAN and broadcasting `GridWorks` with the same
   passphrase brings the whole pico fleet back.
