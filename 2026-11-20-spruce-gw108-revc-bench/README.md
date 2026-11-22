# spruce-gw108-revc-bench, 2026-11-20

> What this is: the first bench run of the Gw108 Rev C on spruce, one
> component class at a time through `starter-scripts/gw108_test_code.py`,
> with the scada stopped. The verdict is in "Found"; the logbook entry is
> the index record. Design: Linear OPS-701.

## Why

Spruce is wired to a Rev C in place of its Rev B. Each component has to
be seen working on the bench before its facts go into the Rev C
device-type record and the spruce layout. The questions in order: do the
zone whitewire inputs follow the thermostats; do the zone relays, driven
one at a time, produce distribution flow as the flow picos report it; does
the heat pump dry contact close.

## Setup

- Spruce, `gridworks-scada` service stopped, starter-scripts at
  `c2021df` on the box. Nothing listens on port 8000 until the
  starter-scripts pico API is started for the window, so the flow picos
  post their ticklists to it and its stdout is the flow record.
- A zone watch loop reads the six whitewire GPIO inputs once a second and
  logs each change with a timestamp (ET). Actuations run from the laptop
  over ssh through the starter script, with expander pin readback after
  each.
- Logs on the box under `/tmp/` for the window, copied into `evidence/`
  at the end.

## Found

Window 1 (baseline, nothing actuated): PASS. Every Rev C native input,
both thermistor ADCs, the CT ADC behind mux channel 4 and the three DACs
answer at the pins, bus and addresses the board-facts spoke states.
Zone whitewires idle at 1, GPIO 19 at 1 with a load on Valve 4,
th1..th4 at 67 to 71 °F, th5..th8 unwired (3.296 V), CT bias about 1.05 V
with ct3 at 2.20 V, Dac2 channel C holding 3040 raw. The pico API took
posts from every microvolts pico and the three BTU meters within a
minute of starting. The thermostat check, the zone relays and the heat
pump dry contact are the next window.

Window 2 (14:14 to 15:45):
PASS on the zone side and on every FCM output tried. Three of four wired
zones follow their thermostats on GPIO 17, 27 and 10 and bring dist flow
at the Caleffi; upstairs (GPIO 22) never calls and lights no board LED,
thermostat suspected. All four zones run under the failsafe plus scada
relay pair with the thermostats idle. Two findings on the plant side,
both in the install rather than the board: the FCM end of the DB25 was
wired to the Rev B pinout, and nothing fed the Rev C AUX 24 VAC input,
which powers every non-zone output. With the FCM end rewired one load at
a time and Zones bridged to AUX: store pump on Pump 2 (5.8 gpm with the
charge-discharge valve open, deadheads with it closed), charge-discharge
valve on Valve 1, secondary pump on Pump 3 (7.8 gpm), heat pump dry
contact starts the heat pump (primary flow 10.7 gpm). Valve 2 and CT1
are the next reads. One bench-tool defect found and fixed on a branch:
the starter script cleared every relay on import.

Window 3 (15:50 to 16:07): PASS. The secondary pump's current on a
clamp meter against Dac3 channel C: 0.2 A at 5 V, 0.6 A at 8.5 V,
0.64 A at full scale, so the pump reaches full speed near 8.5 V. CT1 on
the store pump reads on from off cleanly; the full report is "CT1 on the
store pump" below. Valve 2 confirmed with the meter across DB25 pins 9
and 22. Valve 4 is unused at spruce. The secondary pump's power stays on
the eGauge.

Window 4 (16:20 to 16:40, the roll and admin): PASS for every relay
spruce drives, under the scada on the Rev C names. Spruce rolled to
scada `jm/gw108-revc` (`e9bf4a93`) with tlayouts `c43d091` at 16:20:57
and again with `37b18dc` (the secondary-hx tank module) at 16:24:56; both
boots clean, zero errors, one expected glitch (the secondary 0-10 V
EEPROM reprogrammed from 7.55 to 7.6 V, verified on the second boot).
Under admin: secondary pump relay and 0-10 V, charge valve, store pump,
heat pump call through hp-boss. hp-boss took the secondary pump relay
back from admin on TurnOn, opened it, closed the call at 16:27:16 and
closed the secondary pump relay at 16:27:51 on sensing the heat pump; by
16:30 the outdoor unit drew 1774 W, secondary flow 6.99 gpm, secondary
pump 173 W, store flow 3.66 gpm; on TurnOff at 16:31:45 it opened the
call and opened the secondary pump relay at 16:33:44 once the heat pump
was sensed off. The new secondary-hx probes read 72.4/72.8 °F idle and
79.6/72.5 °F hot/cold with the heat pump on. CT1 under the live scada
with the store pump on: 46 mV RMS, no scada fault during the read. Valve
test: charge valve and iso valve both closed, store flow 0 (deadhead,
proven); iso valve opened at 16:36:50 with the charge valve closed, no
store flow by 16:38, the end of the capture; see "Found, open".

Found, open: whether the store pump can flow with the iso valve open and
the charge valve closed, or needs the charge valve regardless. Store flow
3.66 gpm with the heat pump loop running against 5.8 gpm alone. The
secondary pump relay closed by admin alone at 16:25:23 with the 0-10 V at
3.5 to 4.5 V showed 0 W and 0 flow at 16:27; it ran at once when hp-boss
closed it at 7.6 V. The 0-10 V actor stays with admin when hp-boss takes
the relay back (local-control executor, "Open").

## CT1 on the store pump

Setup: one SCT-013 (100 A : 50 mA, current output) clamped on one
conductor of the store pump's line cord, plugged into the CT1 terminal,
DIP switch 4 on for CT1's 470 Ω burden (the switch numbering is
reversed). ct2..ct4 open. The CT ADC is the ADS1115 at 0x48 behind mux
channel 4, gain 1 (±4.096 V), set to 860 SPS continuous for these reads.
Each read is 1500 samples in about 2.5 s; a real conversion arrives
every 1.9 ms through the mux (about 550 a second, 8 or 9 per 60 Hz
cycle), the rest are repeats. Scripts and samples: `evidence/ct-window3/`.

| Read | Turns | Mean | Min | Max | Peak to peak | RMS about mean |
|---|---|---|---|---|---|---|
| store pump off, secondary pump running | 1 | 1.105 V | 1.104 | 1.106 | 0.002 V | 0.6 mV |
| store pump on (Valve 1 energized, Pump 2) | 2 | 1.131 V | 1.024 | 1.246 | 0.222 V | 41 mV |
| store pump on, two reads 8 s apart | 1 | 1.106 V | 1.028 | 1.182 | 0.154 V | 26.6 mV |
| store pump off again | 1 | 1.105 V | 1.104 | 1.105 | 0.001 V | 0.6 mV |

Findings:

- CT1 reads the store pump. The RMS about the mean is a factor of 45
  (one turn) or 80 (two turns) above the off-state noise, and it returns
  to the bias within 3 s of Pump 2 off. One turn is the install.
- The reading does not change with Dac3 channel B from 1600 to 4095 raw:
  the store pump has no 0-10 V speed wire.
- The waveform is not a sine. In the one-turn run 84% of samples sit
  within ±20 mV of the mean and the rest are short excursions out to
  -80 and +70 mV: a rectifier-fed ECM pump drawing narrow current pulses
  twice a cycle, caught by the sampling only sometimes. A sampled RMS
  over half a second is a steady on/off signal. It is not a current
  meter: on the 0.235 V RMS per amp scale 27 mV reads as 0.11 A, a lower
  bound, since most pulse tips fall between conversions. Amps from a CT
  on this board need a per-pump calibration against a clamp meter, or an
  ADC sampling well above 1 kHz, which this one behind the mux cannot do.
- The ADC bias on an open input is not one number: ct2 reads 1.24 V,
  ct3 2.07 V, ct1 1.105 V with the burden on. A scada reading these
  takes the bias per channel at rest, not a constant.
- An open input shows occasional samples at exactly 1.024 or 1.246 V in
  the first reads after switching channel in continuous mode (ct2 and
  ct4 in the probe); discard the first 30 samples after a channel switch.

## Timeline

- 13:27 baseline reads: bus scan, native inputs all idle, expanders cleared.
- 13:28 ADC and DAC reads: th1..th4 67 to 71 °F, th5..th8 open, CT bias
  about 1.05 V with ct3 at 2.20 V, DACs read back.
- 13:43 pico API started on port 8000; microvolts picos and the three BTU
  meters post within a minute.
- 13:46 zone watch running, baseline [1, 1, 1, 1, 1, 1].
- 13:47 window closed (the box was wanted); API and zone watch stopped,
  logs copied, box tmp cleaned. Next window: thermostats up, zone relays,
  heat pump dry contact.
- 14:14 window 2 opened: starter-scripts pulled to `0b8e836` on the box,
  pico API on port 8000 (secondary BTU posting within seconds), zone watch
  running, baseline [1, 1, 1, 1, 1, 1]. Thermostats next.
- 14:15 to 14:31 thermostats one at a time: bedrooms GPIO 17 (14:15:13),
  living room GPIO 27 (14:21:34), garage GPIO 10 (14:30:44); dist flow
  1.5 to 1.8 gpm per zone, 2.5 gpm with two, 0 within seconds of release.
  Upstairs: no input change, no board LED; thermostat suspected.
- 14:33 to 14:41 zone relay pairs 1..4, each failsafe on, scada on 75 s,
  scada off, failsafe off, in one process: dist flow 1.6, 1.5, 1.8,
  1.9 gpm, 0 after scada off; pin readback matched every command.
- 14:44 to 14:49 Pump3 relay (0x21 port 1 bit 5) with the speed on Z1
  (dac1 A 3040): relay pin 1, secondary CT at rest bias, no secondary
  flow. A second process at 14:46 had dropped the relay: the starter
  script clears the expanders on import.
- 14:50 to 14:52 Pump3 toggled at 5 s with George at the board: the
  relay-side LED follows the bit, the labelled PUMP 3 LED in the FCM box
  stays dark.
- 14:56 George finds the FCM end of the DB25 wired to the Rev B
  alternating-row pinout; Rev C uses the standard pinout (Joe's errata).
  Pump3 released at 14:56:27, every expander bit off. The FCM end is
  rewired to the Rev C pinout before the FCM outputs are retried.
- 15:04 to 15:14 FCM end rewired one load at a time: Valve 1 (pins 20, 8)
  and Pump 2 (pins 6, 19) close with LEDs lit and 0 V at the pins; the
  AUX 24 VAC IN has nothing on it.
- 15:16 Zones bridged to AUX. Pump 2 runs the store pump; 0.66 gpm blip
  then 0 against the closed charge-discharge valve. 15:17 Valve 1
  travels. 15:19 Pump 2 with Valve 1: 5.8 gpm, then a second process's
  import clears Valve 1 and the flow falls to 0 (the clear-on-import
  defect). 15:20 all off, Valve 1 re-energized.
- 15:23 Jessica drives from the REPL. 15:33 Pump 3 and the heat pump dry
  contact: secondary flow 7.8 gpm, primary flow 10.7 gpm, heat pump
  running. Logs copied at about 15:45 with the window still open.

- 15:50 to 15:58 secondary pump current on the clamp meter against
  Dac3 C: 0.2 A at 2000 raw, 0.6 A at 3400, 0.64 A at 4095.
- 16:00 to 16:03 Claude's process, REPL stopped: CT probe of all four
  channels, then speed sweeps against ct2 and ct3, both open inputs.
- 16:03 to 16:05 Valve 1 energized, Pump 2 on, Dac3 B swept 1600 to
  4095: ct1 0.22 V peak to peak at every setting (two turns); released.
- 16:06 CT1 rewound to one turn; rerun: 0.15 V peak to peak, 27 mV RMS,
  two reads 8 s apart within 0.1 mV; released.
- 16:07 Valve 2 confirmed with the meter across DB25 pins 9 and 22.

- 16:20:57 spruce up on `jm/gw108-revc` with the Rev C layout; admin
  active 16:21:20; the secondary-hx pico posting to no actor.
- 16:24:56 second roll with the secondary-hx module; clean boot.
- 16:25:23 admin takes secondary-pump-relay, CloseRelay; 16:25:35 0-10 V
  3.5 V; 16:25:46 charge valve OpenValve; 16:25:56 store pump CloseRelay;
  16:26:08 0-10 V 4.5 V; 16:27:06 0-10 V 7.6 V.
- 16:27:16 TurnOn to hp-boss: relay back to hp-boss, call closed;
  16:27:51 secondary pump relay closed on HpDetectedOn.
- 16:31:45 TurnOff; 16:33:44 secondary pump relay opened on HpDetectedOff.
- 16:32:29 CT1 read under the live scada, store pump on: 46 mV RMS.
- 16:34:16 iso valve CloseValve; 16:34:35 to 16:34:44 charge valve closed
  and reopened by mistake.
- 16:35:51 charge valve closed (both valves closed): store flow 0 at 16:36:30.
- 16:36:50 iso valve OpenValve: no store flow through 16:38.

## Analysis notes

Zone inputs are opto-coupled and read 0 when the thermostat calls.

## Folder contents & experimental method

Everything here is GENERATED by this run: GPIO reads, expander readback
(`evidence/*-window2.log` are the second window's zone watch, pico API
stdout and the relay actuation transcripts)
and pico posts captured while the scada was stopped. A re-run produces a
new dataset. Nothing came from the journal DB.

- `runbook.sh`: the commands, in order.
- `emit_instances.py`: writes the four `instances/hw1.isone.me.versant.keene.spruce.scada-window<n>-gw.experiment.run-001.json`
  verdicts, one per window, through the gwexp snapshot and reads each back:

      uv run python 2026-11-20-spruce-gw108-revc-bench/emit_instances.py

  The folder holds no `gw.readings` instance; the CT sample files are the
  harness's own measurements and have no display view to regenerate.
- `evidence/zone_watch.log`: timestamped zone input changes (box clock, ET).
- `evidence/pico_api.log`: the pico API's stdout, every ticklist post.
- `evidence/scada-journal-window4.log`: the scada's journal, admin and
  hp-boss lines, from the roll on.
- `evidence/snap-store-valve-test.log`: snapshot capture of store flow and
  the valves during the iso/charge valve test.
- `evidence/ct-window3/`: the CT sample files (`t_s,volts` per sample)
  and the three scripts that took them.
