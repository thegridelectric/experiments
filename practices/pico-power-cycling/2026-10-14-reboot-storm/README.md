# reboot-storm, 2026-10-14

> What this is: when did the fleet's pico-cycler start power-cycling
> the 5 V bus a hundred-plus times a day, and does the start line up
> with the fall firmware reflash? Verdict: yes, house by house, at the
> upload of the 2026-09-15 inline-net tank firmware; the mechanism is
> the scada's zero-margin missing rule (a tank pico is missing after
> exactly its 60 s post period) meeting a sync post that the new
> firmware sends up to a second late (see Found; the logbook entry is
> the index record).

## Why

The beech census of 2026-10-14 07:30 counted 180 bus reboots in the
previous 24 h, with oak at 139 and maple at 54. Every reboot drops every
pico on the bus for the better part of a minute, so the storm itself is
a data-loss source, and the only recent fleet-wide change is the pico
reflash of 2026-09-29 to 10-02. The question is whether the storm
started with the reflash, and on which picos.

## Setup

Observational, read-only. Two pulls, no service touched:

- Journal DB (`DB_ANALYST_URL`): every `report.event` per scada from
  2026-09-01 to 10-14, the `pico.cycler.state` series collapsed to
  change-points, one bus reboot = one transition into `RelayOpening`.
  The `single.pico.state` series counted the same way into `Flatlined`
  (only spruce reports it).
- The eleven house pis over ssh: `~/starter-scripts/code_uploaded/`
  listings with md5s, checkout commits, systemd start times. elm and
  elm2 timed out, as on 10-02.

## Found

**Bus reboots per day, by week (daily rows in the CSV):**

| week of | maple | oak | spruce | beech | fir |
|---|---|---|---|---|---|
| 09-01 | 11 | 62 | 7 | 25 | 8 |
| 09-08 | 10 | 52 | 40 | 34 | 46 |
| 09-15 | 9 | 53 | 59 | 54 | 193 |
| 09-22 | 8 | 36 | 4 | 54 | 59 |
| 09-29 | 64 | 88 | 6 | 135 | 83 |
| 10-06 | 96 | 306 | 5 | 224 | 153 |
| 10-13 (one day) | 58 | 129 | 4 | 183 | 123 |

**The step at each Wiznet house is the day its tank picos received
the 09-15 build (`cd8483c2`, gridworks-pico `0ca8a2f`):**

| house | upload (ET) | reboots the day before / that day / the next |
|---|---|---|
| maple | 09-30 10:42, four tanks | 4 / 37 / 70 |
| oak | 09-29 17:21 tank2; 10-01 16:07 all four | 6 / 34 / 77 then 118 |
| fir | 10-01 15:41, four tanks | 22 / 37 / 91 |
| beech | 10-01 15:09 (`e9ab9a28`, the 09-22 build) | 47 / 33 / 94 (10-02, a short day: 118 reports) |

The 10-02 fleet push of the 09-22 build (`e9ab9a28`, params retry
with `machine.reset()`) did not calm anything: every house ran higher
after it (beech 210–250 a day, oak 115–160 with 290 / 591 / 470 on
10-09..10-11, fir 130–185, maple 80–100).

**Spruce, all wifi, moved the other way on the same code.** It ran
30–73 a day from 09-09 (the `beaf60cf` upload) to 09-21 and 3–10 a day
from 09-22 on; its flatlines since 10-01 are spread evenly over buffer,
fancoil, pipes1 and tank1 at about 15 each. So the new firmware is not
bad on a Pico W; the storm is specific to the Wiznet tank picos, which
is the one place the overhaul changed the network path (ethernet
reconnect, backup URL removed "doesn't work on Wiznet").

**Baselines were not clean before the reflash.** beech ran about 50 a
day through September and oak about 53 a day until 09-26, then oak
dropped to 2–6 for 09-27..09-29 with nothing in the upload record to
explain it. fir stepped from 7 to 85 on 09-11 and burst 243 / 616 / 283
on 09-17..09-19, three weeks before its reflash. Those are separate
questions; this run dates the fleet-wide storm, not them.

**What the data cannot say.** Only spruce journals `single.pico.state`,
so which pico flatlines at maple, oak, fir and beech is not in the
journal; the beech census notes (tank2 88, buffer 65, tank3 27 on
10-13) come from the box log. elm has sent no report since 09-01.

**Mechanism (fir, 2026-10-14 03:05–03:40, then the other houses).**
The journal's `ScadaReadTimeUnixMs` is the moment each pico's post
reached the scada. The four fir tank picos post on a steady 59.8 s
rhythm and nothing else (no async posts at `AsyncCaptureDeltaMicroVolts`
2000 with 1000 × 30 averaging), except that about one post in five
arrives 60.8 s after the previous one instead of 59.8 s. The scada on
`main` (`a70c10ea`) declares a tank pico missing when
`time.time() - last_heard > CapturePeriodS`, with `CapturePeriodS` 60
on every tank channel of every house, checked on a 10 s loop
(`api_tank_module.py` `missing()`); the cycler opens the relay on the
first PicoMissing. So any post that arrives more than 60.0 s after the
previous one is a reboot whenever the 10 s check falls inside the late
window. `gap-before-reboot.txt` tests this at every RelayOpening:

| window | reboots | gap since the triggering pico's last post |
|---|---|---|
| fir 10-14 03:05–03:40 | 6 | 60.02, 60.03, 60.04, 60.06, 60.16, 60.62 s |
| maple 10-13 20:00–10-14 08:00 | 31 | 60.02–60.73 s in 29; 79.8 and 83.6 s in 2 |
| spruce 10-13 20:00–10-14 08:00 | 2 | 60.24 s; 59.1 s (the buffer at 58.7) |
| maple 09-20 00:00–12:00, old firmware | 3 | 60.01, 60.02, 60.57 s |

Every reboot has one tank pico at 60.0x s since its last post, on the
old firmware too: the rule was already the trigger at the September
rate. What the 2026-09-15 firmware changed is where the sync post is
sent from. The old main posted from the timer callback itself, so the
post left at 60.00 s and the late window was the network's few
milliseconds. The new main only raises a flag in the callback and posts
when the main loop next reaches it, after three `adc_micros` bursts of
30 × 1000 ADC reads, about a second of work, so one post in five goes
out ~1 s late and the late window is ~0.8 s wide: roughly 8 % of those
late posts are caught, four tank picos, a late post every five minutes
each, and the result is the 100-plus reboots a day seen.

At fir the storm also phase-locks: the relay opens on a 10 s check tick
and closes 5.02 s later, the buffer pico boots and posts 4.91 s after
power in every cycle, and its seventh post falls 0.12 s before a tick,
so a cycle repeats every 370 s (the 310 / 430 / 610 / 670 / 730 s cycles
are the same lattice when the buffer's post squeaks through once). The
wifi flow picos never flatline: their actor's rule is not the capture
period. Spruce's two overnight reboots are the same rule; why spruce
catches it thirty times less often than maple with the same firmware,
the same layout period and the same scada rule is not resolved here.

**Two scada findings beside the rule** (`main` `a70c10ea`, both also in
`actual-spruce`): `api_tank_module.py` compares a timestamp to a
constant (`if self.last_error_report > FLATLINE_REPORT_S`), always true,
so a missing pico re-sends PicoMissing every 10 s rather than every
60 s; and the cycler's post-cycle ignore window ("picos can take 45
seconds") runs from the relay close. `jm/spruce-unlimbo` already
replaces the rule with `PicoLiveness` (missing after 2.5 expected post
periods); nothing on `main` has margin.

## Timeline

- 09-15 21:03 (EU) gridworks-pico `71fe467`..`0ca8a2f`: backup-URL
  mechanism removed ("doesn't work on Wiznet"), inline-net mains added.
- 09-22 08:49 `6a713e1` merged: params post retried until the scada
  answers, late answer resets the pico.
- 09-29 17:21 oak tank2 gets `cd8483c2`; oak 34 reboots on 09-30.
- 09-30 10:42 maple's four tanks get `cd8483c2`; maple 37 that day, 70 next.
- 10-01 15:09–16:07 beech (`e9ab9a28`), fir and oak (`cd8483c2`).
- 10-02 10:02–10:11 fleet push of `e9ab9a28` / `6db14a82`; scadas
  restarted. beech 94, oak 118, fir 91 that day.
- 10-03 onward: beech 200–250, oak 115–160, fir 130–185, maple 80–100
  a day. The pico-cycler walks every house's bus through the night.
- 10-14 07:30 beech census: 180 reboots in 24 h, from the three Wiznet
  tanks flatlining.
- 10-14 03:08–03:33 fir: six cycles 370 s apart, each opened 60.0x s
  after the buffer pico's last post (`fir-scada-log/`, `fir-post-cycles.txt`).

## Analysis notes

- A reboot is a change-point into `RelayOpening`; the first sample of
  each house's series is not counted. Days with fewer than 288 reports
  (one per 5 min) undercount: beech 10-01 (179) and 10-02 (118), spruce
  09-21 (198), maple 09-28 (222), fir 10-01 (255).
- The served firmware has no version or commit string; md5 is the only
  identity (`../firmware-track-record.md`).
- The counts are per house, not per pico: one flatlining pico produces
  the same bus reboot as three.
- The scada logs no pico post; a pico is known alive only by the absence
  of a flatline line. `gap_before_reboot.py` reads liveness from the
  journal's post times instead.
- "Wiznet" was the first guess and is not the discriminator: fir's tank3
  is a Pico W and flatlines as often as its three Wiznet siblings.

## Folder contents & experimental method

The reboot counts come from the immutable store (journal DB,
re-pullable by anyone). The box census is EXTERNAL EVIDENCE: read-only
listings of each pi's filesystem and systemd state taken 2026-10-14
about 08:30 ET, not regenerable (the boxes move on). Nothing running
was touched.

- `pull_reboots.py` — the journal pull; writes the three CSVs. No sema
  word yet states "bus reboots per house per day", so the CSVs are
  committed as the reduced evidence; the word that retires them would
  be a per-day cycler stats word beside `gw.channel.gap.stats`.
- `reboots-by-house-day.csv` — date, house, bus reboots.
- `flatlines-by-pico-day.csv` — date, house, pico handle, flatlines
  (spruce only; the others journal no `single.pico.state`).
- `reports-by-house-day.csv` — date, house, report.event count, to tell
  a short day from a quiet one.
- `box-census/<box>.txt` — raw per-box listing, provenance header on
  each. `box-census/upload-sessions.txt` — the uploads grouped by box
  and two-hour session, derived from those listings.
- `fir-scada-log/` — EXTERNAL EVIDENCE: grep excerpts of fir's
  `journalctl -u gwspaceheat` for 2026-10-13 20:00 to 10-14 08:00
  (cycler lines, the three-cycle timeline, the deployed layout's pico
  parameters), box clock.
- `post_times.py <house> <start> <end> <channel...>` — every post time
  of the named channels at millisecond resolution, from the journal.
  `fir-post-cycles.txt` is its reading for the three cycles.
- `gap_before_reboot.py <house> <start> <end>` — for each RelayOpening,
  seconds since each tank pico's last post; `gap-before-reboot.txt` is
  its output for the four windows in Found.

Regenerate the journal side:

    cd experiments && uv run python pico-power-cycling/2026-10-14-reboot-storm/pull_reboots.py

The mechanism check:

    cd experiments && uv run python pico-power-cycling/2026-10-14-reboot-storm/gap_before_reboot.py fir '2026-10-14 03:05' '2026-10-14 03:40'

Weekly view of the reboot CSV:

    awk -F, 'NR>1{print $1, $2, $3}' pico-power-cycling/2026-10-14-reboot-storm/reboots-by-house-day.csv | sort
