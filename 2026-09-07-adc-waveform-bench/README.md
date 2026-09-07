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
is not wired to a GPIO), so a polled burst cannot promise one clean
conversion per slot. The word therefore carries a host-timed offset per
code; whether those offsets can be dropped in favour of a bare rate is
the first thing this bench decides.

### Claims wanting silicon

1. **The sampling path works**: `capture.py` writes a valid
   `gw.adc.waveform` instance from the chip, in both modes.
2. **Single-shot gives exact conversions** at a measured effective rate
   (expected 400 to 600 per second at the 100 kHz bus), with no
   duplicate-collapsed or mid-slot codes.
3. **Continuous at 860 SPS with change-detection dedupe** either keeps
   one code per slot (offset gaps clustered at 1163 µs) or shows the
   collapse and mid-slot smear the docstring predicts. Either answer
   settles which path the scada actor takes.
4. **The fold recovers the waveform**: on the synthetic instance,
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

**3. Capture, both modes (honeysuckle).** Two seconds each. The last
line printed is the verdict: count, effective rate, largest gap.

    cd ~/experiments/2026-09-07-adc-waveform-bench

    ~/gridworks-scada/gw_spaceheat/venv/bin/python capture.py --mode single --seconds 2 --tag r1

    ~/gridworks-scada/gw_spaceheat/venv/bin/python capture.py --mode continuous --seconds 2 --tag r1

**4. Collect (dev machine).** The instances are the evidence; they come
back by scp from the pi and are committed here. The pi's copy is
removed in the restore step.

    scp 'honeysuckle:~/experiments/2026-09-07-adc-waveform-bench/instances/d1.bench.honeysuckle.ta-*' instances/

**5. Fold (dev machine).** One line per instance; the plot lands
beside it, gitignored.

    uv run python fold.py instances/d1.bench.honeysuckle.ta-p0.single.r1-gw.adc.waveform-000.json

    uv run python fold.py instances/d1.bench.honeysuckle.ta-p0.continuous.r1-gw.adc.waveform-000.json

**6. Restore (honeysuckle).** The clone stays (recorded in the box
README); the run's instances leave the box.

    rm ~/experiments/2026-09-07-adc-waveform-bench/instances/d1.bench.honeysuckle.ta-*

### Reading the offsets

Single-shot: every offset gap is one request round trip (config write,
OS poll, read); the gaps' spread is the bus, not the chip. Continuous:
gaps near 1163 µs are one slot each; a gap near 2326 µs is a collapsed
duplicate; gaps well under 1163 µs mean the chip was read twice in one
slot with a changed value, which should not happen. The histogram of
gaps is the finding for claim 3.

## Found

Open.

## Timeline

Open.

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
- `capture.py` — the pi-side sampler (smbus2, ADS1115 at 0x48); writes
  a `gw.adc.waveform` instance through the vendored class.
- `fold.py` — the laptop-side frequency fit, fold and plot.
- `synth.py` — writes the synthetic dry-run instance.
- `instances/d1.bench.synthetic.ta-p0.synth.60hz-gw.adc.waveform-000.json`
  — SYNTHETIC, from `synth.py`; the fold's fixture, not a measurement.
- `instances/d1.bench.honeysuckle.ta-p0.<mode>.<tag>-gw.adc.waveform-000.json`
  — the captured bursts (generated on the pi, runbook step 3).
- `instances/*-fold.png` — generated by `fold.py`, gitignored.

Regenerate everything from scratch: the runbook above, top to bottom.
There is no CSV view of a waveform instance; the fold's numbers and plot
are the view, regenerated from an existing instance with:

    uv run python fold.py instances/<instance>.json
