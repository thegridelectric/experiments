# adc-waveform-bench, 2026-09-07

> What this is: does the pi plus the gw108's CT ADS1115 deliver clean
> conversions from a current-transformer input, at what effective rate,
> and does folding one to two seconds of them on a fitted mains
> frequency give a composite waveform? Verdict in "Found" once run; the
> logbook line is the index record.

## Why

The gw108's four CT terminal pairs have never been read as waveforms.
Each drives a 470 Ω burden biased at 1.65 V into an ADS1115 at 0x48,
whose ceiling is 860 conversions per second: 14 per 60 Hz cycle, too
few to see a cycle's shape directly. Since 860 is not a multiple of 60,
consecutive cycles land at different phases, so folding a second or two
of samples onto one period, with the frequency fitted from the data,
gives a composite with hundreds of points per cycle. That composite is
what a CT channel's vocabulary (winding ratio, loop count, burden, the
derived scale) will be validated against, and what a scada actor would
one day emit as a `gw.adc.waveform`.

The pi cannot see the chip's conversion-ready signal (the ALERT/RDY pin
is not wired to a GPIO), so the sampler takes one single-shot conversion
per request and stamps it with the host clock: every code is exactly one
conversion, and the rate is what the bus allows, about 390 per second at
100 kHz. The spacing is bus-timed, not chip-timed, so the word keeps a
host-timed offset per code. (Free-running the chip and polling for
changed codes was tried in the 2026-09-07 dry run and dropped; see
Found.)

### Claims wanting silicon

1. **The sampling path works**: `capture.py` writes a valid
   `gw.adc.waveform` instance from the chip.
2. **Single-shot gives exact conversions** at a measured effective rate
   (expected 400 to 600 per second at the 100 kHz bus), with no
   duplicate-collapsed or mid-slot codes.
3. **The fold recovers the waveform**: on the synthetic instance,
   frequency within 0.01 Hz and amplitude within 2 %; on honeysuckle,
   with no CT installed, a flat composite at the 1.65 V bias with the
   residual noise stated in mV.

## Setup

- **Host:** honeysuckle, the bench gw108 (`d1.bench.honeysuckle.ta`).
  No scada running, nothing else on the bus. Bus 1 at the 100 kHz
  default (`/boot/firmware/config.txt` has `dtparam=i2c_arm=on` only);
  raising it to 400 kHz is a lever for a later run and would be box
  state recorded in the box README.
- **Chip:** ADS1115 at 0x48, input P0 single-ended, PGA ±4.096 V (the
  bias sits at 1.65 V and a 40 to 60 W bulb swings about ±0.17 V), data
  rate 860.
- **Code under test:** this folder, from the pi's `~/experiments` clone
  at a pushed SHA, run with the scada venv's python
  (`~/gridworks-scada/gw_spaceheat/venv/bin/python`, which has smbus2
  and pydantic). The experiments repo is public, so the pi clones over
  https with no key.
- **Word:** `gw.adc.waveform/000` (staging), vendored in `src/gwexp/sema`.
- **Fold:** `fold.py` on the laptop, in the experiments venv.

### Runbook

Commands under **dev machine** run from this folder on the laptop.
Commands under **honeysuckle** run in a shell on the pi.

**0. Dry run (dev machine, before the bench).** The fold must recover
the synthetic burst first.

    uv run python synth.py

    uv run python fold.py instances/d1.bench.synthetic.ta-p0.synth.60hz-gw.adc.waveform-000.json

To look at it interactively (zoom, pan, cursor readout; the window
blocks until closed):

    uv run python fold.py instances/d1.bench.synthetic.ta-p0.synth.60hz-gw.adc.waveform-000.json --show

**1. Put the harness on the pi (honeysuckle, once).** The box has no
experiments clone yet; this places it, and the box README records it.

    git clone https://github.com/thegridelectric/experiments.git ~/experiments

    git -C ~/experiments log -1 --format=%h

**2. Confirm the bench is quiet (honeysuckle).** No scada, the chip
answers.

    pgrep -fa "cli.py run" ; /usr/sbin/i2cdetect -y 1 | grep -c 48

**3. Capture (honeysuckle).** Two seconds. The last line printed is
the verdict: count, effective rate, largest gap.

    cd ~/experiments/2026-09-07-adc-waveform-bench

    ~/gridworks-scada/gw_spaceheat/venv/bin/python capture.py --ta-alias d1.bench.honeysuckle.ta --seconds 2 --tag r1

On spruce the alias is `hw1.isone.me.versant.keene.spruce.ta`, the scada
stays running (nothing on the box addresses 0x48), and the channel names
the CT: `--channel P1` is CT2, the secondary pump.

    ~/gridworks-scada/gw_spaceheat/venv/bin/python capture.py --ta-alias hw1.isone.me.versant.keene.spruce.ta --channel P1 --seconds 2 --tag pump1

**4. Collect (dev machine).** The instances are the evidence; they come
back by scp from the pi and are committed here. The pi's copy is
removed in the restore step.

    scp 'honeysuckle:~/experiments/2026-09-07-adc-waveform-bench/instances/d1.bench.honeysuckle.ta-*' instances/

**5. Fold (dev machine).** One line per instance; the plot lands
beside it, gitignored.

    uv run python fold.py instances/d1.bench.honeysuckle.ta-p0.r1-gw.adc.waveform-000.json

**6. Restore (honeysuckle).** The clone stays (recorded in the box
README); the run's instances leave the box.

    rm ~/experiments/2026-09-07-adc-waveform-bench/instances/d1.bench.honeysuckle.ta-*

### Speed ladder (spruce, secondary pump)

`ladder.py` steps the secondary pump's 0-10 V level and captures a CT2
burst at each, so the waveform can be compared across speeds. It drives
the DAC and the pump relay exactly as `spruce_summer_hack.py` does, from
the starter-scripts venv, and calls `capture.py` under the scada venv.
Levels 3.0, 4.5, 6.0, 7.5, 9.0, 10.0 V (the pump's speed band per the
2026-09-06 sweep: linear 3.5 to 8.5 V, maximum from 9 V); 60 s holds so
the pico's flow reading has a chance to land for the label.

    # dev machine: commit + push this folder, then on spruce:
    git -C ~/experiments pull
    sudo systemctl stop spruce-summer-hack.service     # failsafe drops the pump; the driver re-energizes it
    cd ~/experiments/2026-09-07-adc-waveform-bench
    ~/starter-scripts/venv/bin/python ladder.py --run ladder1
    sudo systemctl start spruce-summer-hack.service    # re-asserts the summer posture
    # dev machine:
    scp 'spruce:~/experiments/2026-09-07-adc-waveform-bench/instances/*ladder1*' instances/
    scp spruce:~/experiments/2026-09-07-adc-waveform-bench/ladder1-levels.json .
    # restore on spruce: rm the ladder1 instances and the levels file from the clone

Each instance is tagged `p1.dac<volts x 10>.<run>`; `<run>-levels.json`
holds the level table (volts, DAC code, pico flow with its age, instance
name). The label lives there because `gw.adc.waveform` has no field for
the drive level or the flow; the CT component vocabulary retires it.

### Burden jumper on CT1 (spruce, store pump)

`jumper.py` reads CT1 (P0) once its burden jumper is fitted: P0 and P1
with the store pump off, then with it on, secondary pump running
throughout. Two questions: does the unburdened mirror of CT2 seen in
`pump1` (167 mV rms on P0 with the store pump off) vanish once CT1 is
burdened, and what does a burdened current-type CT read on its own
pump. Relay bits from `store_common.py`'s table (0x21 reg 3: store bit
4, secondary bit 5). The DAC is left at whatever level it holds; the
phases file does not record it, so note it in Found.

    # dev machine: commit + push this folder, then on spruce:
    git -C ~/experiments pull
    sudo systemctl stop spruce-summer-hack.service     # no scada may be up either; the driver checks both
    cd ~/experiments/2026-09-07-adc-waveform-bench
    ~/starter-scripts/venv/bin/python jumper.py --run jump1
    sudo systemctl start spruce-summer-hack.service
    # dev machine:
    scp 'spruce:~/experiments/2026-09-07-adc-waveform-bench/instances/*jump1*' instances/
    scp spruce:~/experiments/2026-09-07-adc-waveform-bench/jump1-phases.json .
    # restore on spruce: rm the jump1 instances and the phases file from the clone

Instances are tagged `<channel>.<phase>.<run>` (`p0.storeon.jump1`);
`<run>-phases.json` records each phase's store pump bit and instance
names.

### Leads lifted on CT1 (spruce, the tie test)

`peek.py` runs on the dev machine and drives one check over ssh: read
the secondary pump relay bit, capture P1 (CT2) then P0 (CT1) with the
box's `capture.py`, copy the instances back, fold both, print a verdict.
The site step it reads: George unscrews CT1's two leads from the CT1
terminal pair (clamp stays on the pipe, jumper stays fitted). With the
leads off, the only path from CT2's signal to P0 is on the gw108, so P0
flat means the clamps share a conductor and P0 still mirroring P1 means
the inputs are tied on the board or terminal strip.

    # dev machine, from this folder; the box already holds capture.py at a pushed SHA
    uv run python peek.py                        # tag defaults to peek<HHMMSS> ET
    uv run python peek.py --run lift1            # a named run

If the pump relay is off the script stops the hack and the scada,
energizes the secondary pump, holds 15 s, captures, and restores both;
with the pump running only the capture happens. About 25 s with the
pump running, about a minute otherwise. `--baseline` captures with the
pump off instead of energizing it and is the pipeline check; `base1`
(2026-09-08 17:50 ET) read 2.7 mV rms on both channels, verdict
INCONCLUSIVE, as it should. Instances are tagged `<channel>.<run>` and
stay here; the box's copies are removed by the script. The verdict thresholds (20 mV floor on P1, P0/P1 under 0.1 flat,
over 0.5 mirrored) sit between the 3 mV pickup and the 170 to 185 mV the
pump has read at its summer level.

### Reading the offsets

Every offset gap is one request round trip (config write, OS poll,
read); the gaps' spread is the bus, not the chip. A gap well above the
cluster is another bus user's transaction (the scada's expander reads,
on spruce) landing between two requests.

## Found

**Dry run, 2026-09-07, on spruce (not the planned honeysuckle first run).**
P0 with no CT jumper fitted, PGA 4096 mV, 860 SPS, two seconds per mode,
the scada service left running (nothing on the box addresses 0x48).

- Sampling path (claim 1): both modes wrote valid instances.
- Single-shot (claim 2): 777 conversions, 388/s, gaps clustered at
  2.5 ms with a few 3.8 to 4.0 ms stalls from the other bus users.
  Every code is one conversion.
- Free-running at 860 SPS with change-detection dedupe (the former
  continuous mode): 1598 kept codes, 798/s, but 60 of 1597 gaps were two
  slots (collapsed duplicates), 77 sat near 1.5 ms and 3 under 0.9 ms.
  It does not deliver one clean code per slot, so the word keeps its
  per-code offsets and the mode was dropped from the sampler; its
  instance stays as the evidence.
- Fold (claim 3): the open input carries a 3 mV 60 Hz pickup on a
  1.633 V bias (residual 0.5 mV, 4 codes), which the fold locks onto at
  59.98 to 60.00 Hz. That is the zero reference for the bulb run, not a
  waveform.
- Second pass (`dry2`), single-shot on all four channels, every pump off
  per the scada snapshot: P0 and P1 sit on the bias (1.637 V) with the
  same 3 mV pickup; P2 and P3 float (1.56 V and 2.19 V) with 17 and
  29 mV residual. Consistent with CTs wired to CT1 and CT2 only, and
  with the secondary pump drawing nothing at the time.

**Secondary pump running, 2026-09-07 12:30 ET (`pump1`, `pump2`).** The
summer schedule had turned the secondary and primary pumps on
(`secondary-flow` 7.39 gpm, `primary-flow` 7.40 gpm, `store-flow` 0,
heat pump in standby at 32 W).

- P1 (CT2, secondary pump) carries a clean periodic waveform: fold at
  59.985 Hz, composite 181 mV rms, noise about the composite 26 mV, 794 mV
  peak to peak on the 1.636 V bias. The shape is not a sine: the
  periodogram puts 91 mV at 60 Hz, 102 mV at 180 Hz and 209 mV at 300 Hz,
  five peaks per cycle. The chain is validated end to end: sampling, the
  fold, and a real CT waveform.
- The fold's original sine-fit residual (171 mV) read as noise when it was
  harmonics; `fold.py` now reports the composite's rms and the noise
  about the composite instead.
- P0 (CT1, store pump, flow 0, no burden shunt) shows the SAME waveform:
  167 mV rms, the same 60/180/300 Hz mix, 728 mV peak to peak, with more
  noise (70 mV). Either both CTs are on the secondary pump's conductor or
  the unburdened CT1 picks the signal up from the adjacent cable; a field
  check settles it.
- P2 and P3 unchanged from the dry run (floating, no periodic content),
  so the signal enters through the CT wiring, not the bias rail.
- The secondary-btu pico's `secondary-pump-ct` stayed at 167 (1.67 V)
  with the pump running, so it is not reporting current either; open.
- Scale is open: 181 mV rms on a 20 A voltage-output CT at a nominal
  333 mV rated output would be 11 A, far above any circulator, so the
  CT2 rating or the number of passes through it is not what the notes
  assume.

**Speed ladder `ladder1`, 2026-09-07 13:05 to 13:12 ET.** Summer hack
stopped for the window, pump relay energized by the driver, six DAC
levels with 60 s holds, DAC and relay restored, hack restarted. Every
level got a pico flow reading within its hold. Waveform rms is the
fold's composite about the bias; fundamental is the 60 Hz peak
amplitude; noise is about the composite.

| DAC V | secondary-flow gpm | waveform rms mV | fundamental pk mV | noise rms mV |
| --- | --- | --- | --- | --- |
| 3.0 | 0.64 | 10.0 | 3.4 | 3.4 |
| 4.5 | 3.04 | 32.5 | 11.3 | 11.2 |
| 6.0 | 5.13 | 87.5 | 37.3 | 23.3 |
| 7.5 | 7.29 | 180.7 | 86.5 | 49.7 |
| 9.0 | 9.00 | 274.0 | 152.8 | 47.6 |
| 10.0 | 8.99 | 261.7 | 152.8 | 100.1 |

- The CT tracks the pump: waveform rms rises about 27-fold from
  minimum speed to maximum while flow rises 14-fold, which is the
  shape of pump power growing faster than flow. 9 V and 10 V give the
  same flow and the same current, matching the sweep's finding that the
  pump is at maximum from 9 V.
- The flows agree with the 2026-09-06 sweep curve at every level
  (0.63, 3.05, 5.2, 7.3, 8.99, 8.98), so the label is trustworthy.
- The fold locks at every level, down to 10 mV rms at minimum speed
  with 3.4 mV noise about the composite, so the chain resolves the
  pump across its whole range on one pass through the CT.
- Still open: the absolute scale (a clamp-meter amps reading against
  one of these levels), and why CT1 mirrors CT2.

**Burden jumper `jump1`, 2026-09-08 16:02 ET.** Jumper fitted on CT1's
burden position on site; no scada up, summer hack stopped, secondary
pump on at the DAC level the window scada left (7.6 V, `secondary-010v`
76 in its last snapshot). A `rig1` P1 capture at 15:57 with the window
scada still running, same pump level, folded at 184.7 mV rms, the
ladder's 7.5 V row.

| capture | waveform rms mV | fundamental pk mV | noise rms mV |
| --- | --- | --- | --- |
| P0, store pump off | 184.3 | 89.3 | 21.4 |
| P1, store pump off | 174.3 | 92.0 | 61.5 |
| P0, store pump on | 771.6 | 147.4 | 255.6 |
| P1, store pump on | 737.4 | 146.1 | 307.6 |

- P0 and P1 carry the same signal in both phases: the same five-peak
  shape with the store pump off, the same four-fold rise with both pumps
  running (samples 0.13 to 3.2 V on the 1.64 V bias, inside the 4.096 V
  full scale). The jumper changed nothing on P0 (167 mV rms unburdened in
  `pump1`, 184 with the burden), so P0 is not reading a current-type CT
  of its own; both inputs read what CT2's input carries, and that
  carries both pumps. Either both CTs sit on one conductor feeding both
  pumps, or the two inputs are tied in the wiring or on the board. The
  field check is where the clamps are and a P0 capture with CT1's leads
  off the terminal.
- With both pumps on, the noise about the composite rises to 256 and
  308 mV: the two currents are not one steady periodic shape, so the
  fold's residual is the second pump's contribution drifting in phase,
  not bus noise.

**Graphing the ladder.** Each row of the table is one instance,
`instances/hw1.isone.me.versant.keene.spruce.ta-p1.dac<V x10>.ladder1-gw.adc.waveform-000.json`
(`dac030` is 3.0 V, `dac100` is 10.0 V). `fold.py` draws one level; run
it from this folder in the experiments venv:

    uv run python fold.py instances/hw1.isone.me.versant.keene.spruce.ta-p1.dac075.ladder1-gw.adc.waveform-000.json
    uv run python fold.py instances/hw1.isone.me.versant.keene.spruce.ta-p1.dac075.ladder1-gw.adc.waveform-000.json --show

The first form prints the pump drive level and flow, then the row's
numbers (fundamental, waveform rms, noise), and writes
`<instance>-fold.png` beside the instance with the drive level and flow
in the plot title; `--show` also opens the interactive window. `fold.py`
finds the level by looking the instance up in `ladder1-levels.json`
beside it, so run it from this folder. All six at once:

    for f in instances/*.dac*.ladder1-*.json; do uv run python fold.py "$f"; done

The whole ladder on one axis, five cycles of each level's composite laid
end to end in rising DAC order, each segment labelled with drive, flow
and rms (`instances/ladder1-staircase.png`, generated):

    uv run python staircase.py --run ladder1

Each png has two panels: the first 100 ms of raw conversions, and the
fold with the composite over the samples. Read them in DAC order
(`dac030` up to `dac100`): the five-peaks-per-cycle shape is already
there at 4.5 V and only grows in amplitude from there; 3.0 V is the
pickup-sized trace. The y axis is the channel's volts on the 1.636 V
bias, not current, since the scale is still open. The pngs are
generated and gitignored, so regenerate rather than commit them.

## Timeline

- 2026-09-07 10:50 ET: dry run on spruce, both modes, from clone
  `193f126`; instances collected and removed from the box.
- 2026-09-07 11:05 ET: `dry2`, single-shot on P0..P3; scada snapshot
  at 11:14 showed all flows zero (summer OFF posture).
- 2026-09-07 12:28 ET: `pump1` (P1, P0) and 12:33 `pump2` (P2, P3, P1)
  with the secondary pump running; instances collected and removed from
  the box.
- 2026-09-07 13:05 ET: `ladder1` from clone `63e7bdc`, hack stopped
  13:04, restarted 13:13; instances, levels file and log collected and
  removed from the box.
- 2026-09-08 15:57 ET: `rig1`, P1 with the window scada running
  (scada-owned pump at 7.6 V); collected and removed from the box.
- 2026-09-08 16:02 ET: `jump1` from clone `84352c7`, jumper on CT1,
  hack stopped since 14:24 for the admin rig, no scada up; instances
  and phases file collected and removed from the box.

## Analysis notes

- Codes are the chip's raw conversion-register values, signed 16-bit,
  32767 at positive full scale. Codes to volts: code × FullScaleMillivolts
  / 32768 / 1000. At 4096 mV full scale one code is 125 µV, and the
  1.65 V bias sits near code 13200.
- The fold's amplitude on a no-signal channel is the largest spectral
  line in the band, a noise figure, not a waveform.
- Honeysuckle has no CT on P0, so run 1 says nothing about a CT's
  scale; the spruce runs (bulb, secondary pump) carry that.

## Folder contents & experimental method

All data in this folder is GENERATED by the experiment's own harness on
the bench pi: the chip is read directly over i2c, nothing is in the
journal DB or the S3 eventstore, and a re-run produces a new instance,
never a regeneration. No service was stopped: the bench runs no scada.

- `README.md` — this record.
- `capture.py` — the pi-side single-shot sampler (smbus2, ADS1115 at
  0x48); writes a `gw.adc.waveform` instance through the vendored class.
- `fold.py` — the laptop-side frequency fit, fold and plot.
- `staircase.py` — one figure of a ladder run: five composite cycles per
  level, end to end.
- `synth.py` — writes the synthetic dry-run instance.
- `instances/d1.bench.synthetic.ta-p0.synth.60hz-gw.adc.waveform-000.json`
  — SYNTHETIC, from `synth.py`; the fold's fixture, not a measurement.
- `instances/hw1.isone.me.versant.keene.spruce.ta-p0.<single|continuous>.dry-gw.adc.waveform-000.json`
  — the 2026-09-07 dry-run bursts from spruce, one per mode of the
  sampler as it then was.
- `instances/hw1.isone.me.versant.keene.spruce.ta-p<0-3>.single.dry2-gw.adc.waveform-000.json`
  — the four-channel single-shot pass from the same dry run.
- `instances/hw1.isone.me.versant.keene.spruce.ta-p<n>.single.pump<1|2>-gw.adc.waveform-000.json`
  — the secondary-pump-running captures (P0, P1 at 12:28; P2, P3, P1 at
  12:33).
- `instances/hw1.isone.me.versant.keene.spruce.ta-p1.dac<volts x 10>.ladder1-gw.adc.waveform-000.json`
  — the six speed-ladder bursts on CT2 (runbook "Speed ladder").
- `ladder1-levels.json` — the ladder's level table (DAC volts and code,
  pico flow with its age, instance name); GENERATED by `ladder.py`.
- `ladder.py` — the speed-ladder driver (starter-scripts venv on the
  box; DAC + pump relay as the summer hack does).
- `instances/<ta>-p0.<tag>-gw.adc.waveform-000.json`
  — the captured bursts (generated on the pi, runbook step 3).
- `instances/*-fold.png` — generated by `fold.py`, gitignored.

Regenerate everything from scratch: the runbook above, top to bottom.
There is no CSV view of a waveform instance; the fold's numbers and plot
are the view, regenerated from an existing instance with:

    uv run python fold.py instances/<instance>.json
