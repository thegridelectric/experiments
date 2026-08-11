# ads-declared-rate, 2026-08-10

> What this is: does the unlimbo scada, booted from a sema layout that
> DECLARES its ADS conversion rate, actually read the chip at that
> rate? Bench rung PASSED both pairings 2026-08-10; the spruce window
> (real thermistors) is the remaining rung. The pre-promote EDD gate
> for the hardware vocabulary.

## Why

The hardware words (sema `1d02655`) made the ADS data rate declared
configuration: the menu (`SupportedDataRatesSps`) on the board record,
the choice (`DataRateSps`) on the reader component, a stashed layout
axiom coupling choice to poll rate. Before that closure promotes to
published — freezing every shape — the declaration must be shown to
reach silicon on the scada's own read path: config words built from
`DataRateSps` (`drivers/ads1115.py`), reads serialized through
`I2cBus`, the readback gate re-checking every conversion (a pass
proves the DR bits round-tripped — a garbled or defaulted rate cannot
hide). While everything is staging, anything this experiment surfaces
is an in-place fix, not a new published version.

The prior ads-noise experiment (`../2026-08-06-ads-noise/`)
established what 8 SPS does for noise using its own bench harness;
this one verifies the SCADA's path and anchors the coupling axiom's
constants at two operating points:

- **8 SPS @ 1 Hz** — the settled fleet configuration. Expected sweep:
  4 × (125 + ~10) ≈ 540 ms of 1000 (~54 %).
- **16 SPS @ 2 Hz** — the fallback pairing if a faster poll is ever
  wanted. Expected sweep: 4 × (62.5 + ~10) ≈ 290 ms of 500 (~58 %).

## Setup

The honeysuckle bench pi + gw108 (standard chip map: ADS1115s
0x48/0x49, expanders 0x20/0x21, TCA9548A mux 0x70, three MCP4728s
behind mux channels 1–3). Zero cooling stakes; no deployed service on
the pi, so nothing was stopped for the windows. Identity
`d1.bench.honeysuckle` (dev universe); broker: the pi's own mosquitto
at `localhost:1883` (password-protected; `bench` user recorded in the
pi's `~/README.md`, password only in the pi's scada `.env`) — the
universe guardrail passes (`localhost ⇒ d1`), no LAN, no tunnel.

Code under test: gridworks-scada `jm/spruce-unlimbo` `7b734d85` in the
pi's `~/gridworks-scada` checkout. Artifacts: tlayouts `jm/spruce`
`312f558` — `output/honeysuckle/` (8 SPS @ 1 Hz) and
`output/honeysuckle-16sps-2hz/` (16 SPS @ 2 Hz), both generated from
the same minted identity and id reference, placed at the pi's default
config paths and md5-checked before each run. Two bounded 75 s boots
(`timeout 75 venv/bin/python cli.py run`), one per pairing.

## Found

**Both pairings PASS.** Zero i2c errors, zero readback mismatches,
clean bounded shutdowns; exactly four `i2c-thermistor-broken` glitches
per run — one per floating bench channel, the designed classification
(bench inputs read rail voltage without thermistors wired).

The per-channel glitch timestamps of the first sweep are the timing
measurement (4 samples per run):

- **8 SPS @ 1 Hz:** inter-channel deltas 138/136/137 ms ⇒ gated read
  ≈ 137 ms (125 ms conversion + ~12 ms bus-path overhead); 4-channel
  sweep ≈ 548 ms of the 1000 ms poll — **55 % occupancy**.
- **16 SPS @ 2 Hz:** deltas 75/74/75 ms ⇒ ≈ 75 ms (62.5 + ~12.5);
  sweep ≈ 300 ms of the 500 ms poll — **60 % occupancy, exactly at
  the proposed 0.6 slack bound.**

**The declared rate reaches silicon.** The only difference between the
two artifacts is the layout's `DataRateSps` (+ poll cadence), and the
measured conversion time moved 137 → 75 ms — the DR bits the reader
writes from the component record demonstrably set the chip's
integration time, with the readback gate confirming the config word
on every conversion in both runs.

**Constants finding for the stashed `ThermistorSweepFitsPoll` axiom:**
the serialized bus path costs ~12–13 ms per read over the conversion
time — more than the ~10 ms the ads-noise direct harness measured
(async round-trip through the bus actor). At 13 ms the 16 SPS @ 2 Hz
fallback computes to 302 ms of 500 — right at the 0.6 bound. Decision
at axiom authoring: overhead ~13 ms with slack 0.65, or keep 0.6 and
accept the fallback pairing is marginal by construction. The settled
8 SPS @ 1 Hz pairing has comfortable slack either way.

Bonus catch (the gate working): the first boot attempt refused the
artifacts — gwsproto's `GNodeGt` mirror was pinned at `g.node.gt/005`
while sema published 006. Fixed in scada `7b734d85` before the runs.

## Timeline

- 18:11 ET — pairing A boot (8 SPS @ 1 Hz): reader up at 0x49 through
  `I2cBus`, four broken-glitches at 137 ms spacing, 75 s window, clean
  shutdown.
- 18:13 ET — pairing B boot (16 SPS @ 2 Hz): same shape at 75 ms
  spacing.
- Standing state restored after the runs: the 8 SPS @ 1 Hz primary
  artifact, md5-checked.

## Analysis notes

- The timing evidence is the FIRST sweep's glitch timestamps — four
  samples per run (the broken-glitch warns once per streak, so later
  sweeps leave no per-read timestamps). A longer instrumented window
  would tighten the estimates; the contrast between pairings (137 vs
  75 ms) is far outside any plausible jitter.
- Temperature values are NOT in scope here — bench inputs float at
  rail voltage by design. Real temperatures are the spruce window's
  job, where the four zone thermistors are wired.
- The two shutdown `CancelledError: IOLoop.stop` tracebacks in each
  log are the bounded-timeout kill, not runtime errors.

## Folder contents & experimental method

**How the data was obtained:** everything here was GENERATED by this
experiment — two bounded boots of the scada-under-test on the bench
pi, logs captured from the runs. Nothing came from the immutable
store, and no running service was touched (the bench pi deploys
nothing). A re-run produces a NEW dataset, never a regeneration.

- `bench-boot-8sps.log` — pairing A's full boot log (stdout+stderr of
  the bounded run), copied verbatim from the pi.
- `bench-boot-16sps.log` — pairing B's, same.

**To repeat** (each run makes a new dated dataset; date the log
filenames). Artifacts regenerate from tlayouts `jm/spruce` and the
sibling scada checkout must be on `jm/spruce-unlimbo` (the tlayouts
gens run with the scada venv):

    cd ~/GridWorks/tlayouts
    ../gridworks-scada/gw_spaceheat/venv/bin/python honeysuckle_sema_gen.py

Place a pairing's artifacts on the pi (md5-check both files), boot,
retrieve the log — pairing A shown; for pairing B substitute
`output/honeysuckle-16sps-2hz/` and a `-16sps` log name:

    scp output/honeysuckle/gw.nolan.layout.json honeysuckle:.config/gridworks/scada/hardware-layout.json
    scp output/honeysuckle/gw.house0.operational.params.json honeysuckle:.config/gridworks/scada/hardware-layout/gw.house0.operational.params.json
    ssh honeysuckle 'cd ~/gridworks-scada/gw_spaceheat && timeout 75 venv/bin/python cli.py run > /tmp/bench-boot-8sps.log 2>&1; true'
    scp honeysuckle:/tmp/bench-boot-8sps.log bench-boot-<DATE>-8sps.log

Read the timing from the run's first sweep:

    grep "thermistor-broken" bench-boot-<DATE>-8sps.log

Leave the pi on the 8 SPS @ 1 Hz primary artifact afterwards (the
standing state).
