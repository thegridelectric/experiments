# ads-noise, 2026-07-30 & 2026-08-06

ADS1115 noise floor: poll rate + smoothing (spruce, wired thermistors).

## The design question

Should the scada's i2c thermistor reader use averaging? The reader (gw108
zone thermistors through the ADS1115) currently takes raw single-shot
reads at 128 SPS (samples per second — the chip's conversion rate; at
128 SPS each conversion integrates the signal for ~8 ms), polled at
1 Hz — no smoothing of any kind. The retired
tsnap code polled at 5 Hz and applied an exponential moving average
(α=0.2), so there is precedent in both directions. Before canonizing the
reader as the fleet default we needed to know whether the raw reads are
noisy enough to justify smoothing — either an EMA in software or the
chip's own slower integrating rate (8 SPS) — measured on real wired
thermistors, not assumed.

**The chip's data rate, and polling ceilings.** SPS = samples per
second — the ADS1115's conversion rate, set in the config word of every
conversion (nothing persistent on the chip): 8, 16, 32, 64, 128, 250,
475, or 860 SPS, with 128 the chip default. One conversion takes
~1/SPS, so the data rate is really an **integration-time choice**: at
128 SPS the chip looks at the signal for ~8 ms; at 8 SPS it integrates
for ~125 ms — 16× more in-chip averaging before the value leaves
silicon, with no software state.

The 5 Hz precedent was configuration, not silicon: the TSnap1 hardware
used the same ADS1115 chip (three of them — 0x48, 0x49, 0x4b — for 12
thermistor channels), and its 200 ms floor is a declared layout value
(`layout_gen/multi.py` `MinPollPeriodMs=200`), sized to roughly one
full 12-channel single-shot sweep; the actor's own software floor is
40 ms (`FASTEST_POLL_PERIOD_MS`). Measured on the spruce pi (clean-run
capture): a readback-gated single-shot read costs **16 ms median** at
128 SPS, so a gated 4-channel sweep runs ~64 ms — ~16 Hz ceiling; at
8 SPS the conversion dominates (~135 ms/read) — ~1.9 Hz sweep ceiling,
still ample headroom for the 1 Hz poll. Under bus contention the gated
read stretches ~4× (61 ms in the collision run) — a shared-bus
signature in its own right.

**Conclusion: 8 SPS at 1 Hz poll is better all around.** The
non-default slower rate cuts electrical noise ~40 % on the quiet
channels (in-chip integration, no software EMA needed), and its higher
sd on zone3-upstairs is a virtue, not a penalty: it is catching the
known real temperature variation up there (the thermistor sits near a
fan coil; see the heat-call corroboration in the 08-06 clean-run
findings). A reader whose job is to report real zone temperature wants
exactly that: integrate away electrical noise, render real drift
faithfully. The only reason to prefer 128 SPS would be a need for
>2 Hz sweeps, which the 1 Hz reader has no use for.

Three runs: 07-30 (summary statistics only), and an 08-06 pair with raw
per-sample capture — a collision-contaminated window kept as a
signature library, then a clean window. Together they settle the
question — see the conclusion above: 8 SPS at 1 Hz.

## Found (2026-07-30 run · PASS)

**Found (PASS):** on spruce's four wired zone thermistors (thermistor ADS
0x49 only; deployed scada stopped for the window; summer hack untouched),
120 s per mode, readback-gated single-shot reads, **0 i2c errors and 0
readback mismatches across ~3,360 sequences**:

- baseline 128 SPS @ 1 Hz raw: sd 344–390 µV ≈ **0.011–0.012 °C**,
  p2p ≤ 1875 µV (≈ 0.06 °C)
- 5 Hz + EMA α=0.2 (sd of the filter OUTPUT): 115–291 µV ≈ 0.004–0.009 °C
- 8 SPS @ 1 Hz raw: sd 214–450 µV ≈ 0.006–0.013 °C (helped three zones,
  slightly worsened zone3-upstairs)

Baseline noise sits ~45× below the 0.5 °C async threshold — noise alone
does not force a reader change. (The settled choice is nonetheless
8 SPS — the revised conclusion under "The chip's data rate" above: the
run's own data shows 8 SPS both quieter electrically and faithful to
real drift.) A filter's output variance is lower
by construction, so the EMA row is not a discovery in itself; the finding
is that its ~2–3× reduction matches the √5 white-noise prediction —
sample-to-sample noise on this board is mostly uncorrelated, so any future
averaging can be sized by arithmetic. Exception: zone3-upstairs improved
least and worsened at 8 SPS — a low-frequency component (drift or pickup)
smoothing cannot remove; the channel to look at if any. EMA costs where it
would matter (fast pipe transients): ~1 s lag as configured, and 5 Hz × 4
channels ≈ 30 % serialized-bus occupancy once relay ops share the bus.
Reproducer: `ads_noise_experiment.py` in this folder (deployed scada
must be stopped to re-run); 07-30 summary: `results-summary.json`.

## Found (2026-08-06 re-runs · raw capture) — collision, then clean

Same three modes, same harness plus raw per-sample capture (every read
timestamped to JSONL; EMA mode records pre- and post-filter values;
errors get their own timestamped lines). Two windows were run.

**Run 1 (11:00 ET) — INVALID as board-health data; kept as a signature
library.** The window protocol left the `gwspaceheat-restart` watchdog
timer running as a safety net; it fired 35 s after the stop (systemd
timer accuracy, compounded by ~66 s pi↔laptop clock skew) and restarted
the scada under the harness — **two masters on one ADS** for the rest
of the window. The signature, now on file in the `*-collision.*` data:
104 config-readback mismatches where the register returns the *other
reader's* mux bits, paired ±100–150 mV cross-channel spikes appearing
simultaneously in the harness capture and the archived fleet channels,
and gated reads stretched ~4× by bus contention (61 ms vs 16 ms
median). Anything that looks like this is a concurrency bug, not a
sick chip.

**Run 2 (11:29 ET, clean: watchdog timer stopped, no-scada-process
verified, pi-side transient failsafe armed).** **Zero errors across
~3,360 sequences** — matching 07-30. No spikes; p2p ≤ 6.8 mV. The ADS
is healthy; run 1's "degraded board" reading is retracted. Baseline sd
(626–1911 µV) sits 2–5× above the 07-30 floors, but the EMA mode's
output sd matches the raw sd (on 07-30 the EMA cut it ~3×) — variance
an EMA cannot reduce is not white noise but real slow signal: midday
air movement with cooling active. Zone 3 is the extreme case (its
thermistor sits near a fan coil, so it reads real air fluctuation from
the unit), which also reframes 07-30's observation that 8 SPS "helped
three zones but slightly worsened zone3-upstairs" — the higher sd is
longer in-chip integration faithfully *catching* real variation, not a
worsening. **Heat-call corroboration:** the archive shows zone 3's
thermostat duty-cycling ~14 min on / ~15 min off all morning, and this
window fell in an off-phase (call dropped 11:22:27, next call
11:37:33 — right after the window closed). The run's own numbers show
the consequence: zone 3's mean rose monotonically across the three
modes, 22.63 → 22.77 → 22.88 °C — the ~0.25 °C post-call recovery ramp
of the room re-warming after its fan coil stopped. The "drift" is real
thermal dynamics tied to the fan-coil cycle. Electrically the board is
as quiet as ever: 8 SPS floors 254–402 µV on zones 1/2/4, near 07-30's
214–246 µV.

Data: `results-summary-2026-08-06-clean.json` +
`raw-samples-2026-08-06-clean.jsonl` (the valid run);
`results-summary-2026-08-06-collision.json` +
`raw-samples-2026-08-06-collision.jsonl` (the signature library).

**Layout and constants provenance.** The committed runs (07-30 and
both 08-06 windows) predate the harness's layout de-hack: their
summaries' temperature columns were computed with then-hardcoded
constants, including a 5.65 kΩ series value the Gw108 RevC schematic
disproves (four 5k6 0.1% divider resistors) — a ~0.2 °C bias on those
printed means; sd conclusions unaffected. The sema instances are free
of that bias: the emitter recomputes temperatures from the raw µV
using the reader-component instance in this folder (5.6 kΩ), the
record the box actually declared. The CURRENT harness reads the box's
live layout at run time, refuses to run without the
`i2c.thermistor.reader.component.gt` record, and echoes everything it
used — constants, layout sha256, decode path — into a `board` section
of its results, so every future run carries its own provenance.

## Canary datasets (archive + bench, for the semafy)

The deployed scada reports raw `zone*-gw-microvolts` (133k readings
back to March), so ADS health is computable from the archive:
`canary_daily_stats.py` over `archive-zone-uv-2026-07-14-to-08-06.csv`
counts consecutive-reading jumps >50 mV within 5 min — no real zone
temperature moves that fast, so each is an electrical event. The daily
view: clean 07-14→25, first spikes 07-26 (zones 1/3/4), a cluster
07-29–30 (the incident window), remission 07-31→08-05, and an 08-06
"flare" that is exactly run 1's collision seen from the scada's side.

The three canary datasets, chosen deliberately pre-7/30 (so the ADS
story never has to be disentangled from the 0x21/dac3 incident that
humans won't remember the details of):

- **Clean archive day — 2026-07-22** (full day): zero spikes on all
  four zones, max jump 2.1–13.5 mV, median jump 500–1250 µV.
- **Glitch-active archive window — 2026-07-26 20:30–23:15 ET**: the
  first-spike evening, three days *before* the incident, no work
  session onsite — the genuine precursor. 2/0/5/8 spikes per zone,
  jumps to 75 mV. (The larger 07-29–30 cluster overlaps the incident
  and its diagnostic sessions, so it stays out of the canary set.)
- **Clean harness run — 2026-08-06 run 2** above (on the real
  deployed spruce board; "harness" = data this experiment generated,
  vs "archive" = windows over immutable-store data).

The canary claim these support: per-channel daily spike counts from
already-archived microvolt channels flagged the board corner three
days before its chips failed.

## Folder contents & experimental method

**How the data was obtained — two different origins:**

1. **Archive data (immutable store).** The `gw.readings` instance holds
   readings the DEPLOYED, RUNNING scada reported in normal operation
   (07-14 → 08-06), pulled from the journal database. Anyone can
   re-pull it; the experiment never touched the system to get it. The
   two `-archive` datasets in `instances/` are computed from it.
2. **Harness data (generated by this experiment — in no store).** The
   raw captures and summaries came from STOPPING the deployed scada
   (and its restart watchdog — the one-master rule) for a ~7-minute
   window and running this folder's own reader against the ADS. These
   measurements exist only here; re-running creates a NEW dataset. The
   `-harness` dataset in `instances/` is computed from them.

- `ads_noise_experiment.py` — the bench harness (runs ON the spruce pi
  from the repo clone, deployed scada AND its restart-watchdog stopped
  for the window). Board facts come from the box's own hardware layout,
  decoded through the sema snapshot where the record's version allows;
  results carry `board` provenance including the layout's sha256.
- `results-summary.json` — the 07-30 run's summary (evidence; wire
  shapes, pre-raw-capture harness).
- `results-summary-2026-08-06-clean.json` +
  `raw-samples-2026-08-06-clean.jsonl` — the valid 08-06 run: summary
  plus every sample timestamped (EMA mode records pre- and post-filter;
  errors get their own lines).
- `results-summary-2026-08-06-collision.json` +
  `raw-samples-2026-08-06-collision.jsonl` — the invalidated first
  window, kept deliberately: the two-masters-on-one-ADS signature
  library.
- `hw1.isone.me.versant.keene.spruce.ta-gw.readings-000.json` — the
  archive data: the four zone-microvolt channels' words and readings
  (07-14 → 08-06, 136k readings) pulled from the journal database as
  one validated instance. Re-pullable at will (see below).
- `hw1.…spruce.scada-layout.lite-1786028416399-hw1.ear.json` — the
  scada's own layout.lite emission from the immutable store (S3
  eventstore, 08-06 11:00 ET — the layout live at the clean run):
  source of the noise-stats channel pairings and the host GNode alias.
- `i2c.thermistor.reader.component.gt-000.json` — the thermistor-reader
  component instance the runs consumed (extracted from the then-deployed
  box layout; layout.lite does not carry reader components): the
  electrical constants (5.6 kΩ, 3.3 V, per-channel betas) behind the
  temperature recomputation. Valid at its own version; its 001→002
  upgrade is context-dependent by design.
- `canary_daily_stats.py` — daily spike counts per channel from the
  gw.readings instance (the canary view). Run:
  `uv run python canary_daily_stats.py`.
- `emit_instances.py` — constructs `instances/` through the sema
  snapshot: the clean run's `gw.experiment.run`, per-mode
  `gw.channel.noise.stats` (µV paired with the -gw-microvolts channels,
  temperatures with -gw-temp), and `gw.channel.jump.stats` for the two
  archive canary windows. Regenerate: `uv run python emit_instances.py`.
- `instances/` — the sema-typed results, one subfolder per DATASET
  (a distinct measurement context), named `<date>-<label>`: `-harness`
  datasets are measurements this experiment generated on the real
  hardware (a new run on a new day = a new subfolder); `-archive`
  datasets are windows computed over immutable-store data. CSV views
  via the repo-top `stats_display.py`, generated on demand and
  gitignored.

**Generate new experimental data:** unlike the archive datasets, the
harness data does NOT exist in any immutable store (journal DB, S3
eventstore) — it is measurement created by running this experiment on
the real spruce board. Re-running does not regenerate the committed
data; it produces a NEW dataset: new dated results files, a new
`instances/<date>-<label>-harness/` folder, and an `emit_instances.py`
extension to cover it.

The run window, line by line (the one-master rule: the deployed scada
AND its restart watchdog must be stopped — the watchdog alone restarts
a stopped scada within seconds, which is how the 08-06 collision
happened; the transient failsafe restores everything after 20 min even
if you disconnect mid-run):

    ssh spruce
    cd ~/experiments && git pull
    sudo systemd-run --on-active=20m --unit=ads-exp-failsafe /bin/sh -c "systemctl start gwspaceheat gwspaceheat-restart.timer"
    sudo systemctl stop gwspaceheat-restart.timer gwspaceheat
    systemctl is-active gwspaceheat        # must print "inactive"
    cd 2026-08-06-ads-noise && ../.venv/bin/python ads_noise_experiment.py
    sudo systemctl start gwspaceheat gwspaceheat-restart.timer
    systemctl is-active gwspaceheat        # must print "active"
    sudo systemctl stop ads-exp-failsafe.timer
    exit

Then from the laptop, bring the new dataset home (date the filenames):

    scp spruce:/tmp/ads_noise_results.json 2026-08-06-ads-noise/results-summary-<DATE>-harness.json
    scp spruce:/tmp/ads_noise_raw.jsonl 2026-08-06-ads-noise/raw-samples-<DATE>-harness.jsonl

**Pull additional archive data (different days):** the committed
`gw.readings` instance covers 07-14 → 08-06; to extend the canary view
to newer days, re-pull with a wider window — same command, new
`--end` (needs `GJK_DB_URL` in `experiments/.env` and AWS credentials
for the eventstore; from the repo top):

    uv run python pull_readings.py \
        --ta hw1.isone.me.versant.keene.spruce.ta \
        --like 'zone%gw-microvolts' \
        --start '2026-07-14 00:00' --end '<NEW END, e.g. 2026-08-20 00:00>' \
        --out 2026-08-06-ads-noise

This REPLACES the instance (same filename; its WindowStart/End fields
carry the new bounds) — the archive data is re-pullable at will, which
is exactly what distinguishes it from harness data. Then rebuild:
`canary_daily_stats.py` covers the new days automatically; to turn a
newly interesting window into a dataset, add its
`(<date>-<label>-archive, start, end)` row to the window list in
`emit_instances.py` and re-run it.

The instances rebuild locally (from the repo top):

    uv run python 2026-08-06-ads-noise/emit_instances.py
    uv run python 2026-08-06-ads-noise/canary_daily_stats.py

**Display CSVs from the existing instances** (from the repo top;
values convert to mV via the channel words carried in this folder's
gw.readings instance):

    uv run python stats_display.py 2026-08-06-ads-noise/instances/2026-07-22-clean-archive/*-gw.channel.jump.stats-000.json
    uv run python stats_display.py 2026-08-06-ads-noise/instances/2026-07-26-glitch-archive/*-gw.channel.jump.stats-000.json
    uv run python stats_display.py 2026-08-06-ads-noise/instances/2026-08-06-clean-harness/*-gw.channel.noise.stats-000.json

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only — the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from \
        hw1.isone.me.versant.keene.spruce.ta-gw.readings-000.json
