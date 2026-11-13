# Sieg valve travel vs flow timing (maple, 2026-09-27 and 2026-09-28)

Status: Draft · Pass 0 · Updated 2026-09-28

When the keep leg (`sieg-flow`) and send leg (`sieg-send`) start and stop changing, measured against the `sieg-loop` motor start and stop. Times are box ET. `t+` is seconds from motor start. Flow values are in gpm.
Source tags: **RE** = report.event reading (pico stamp), **LOG** = sieg-loop log line, **STRIP** = `sieg-view` value with age.
"Settled" means the last reading outside the post-stop band. For the send leg the band is the post-stop mean ±0.07 gpm (±0.10 for T3, which jitters more). For the closing leg it is the reading that reaches 0.
Scripts in this folder: `travel_flow_dump.py`, `travel_analyse.py`. Dumps: `travel-dump-0927.txt`, `travel-dump-0928.txt`.

## Summary

| travel | direction | motor s | first change (closing leg / opening leg) | flow settled | motor after settled |
|---|---|---|---|---|---|
| Run 1, 09-27 boot | keep → send | 110.3 | ≤23.6 / 37.6 | t+78.7 | **31.5 s** |
| Run 2 A, 09-28 boot | keep → send | 110.2 | ≤24.6 / 38.2 | t+79.1 | **31.1 s** |
| Run 2 D, admin | send → keep | 110.1 | 18.3 / 30.4 | t+86.4 | **23.7 s** |
| Run 2 T3, admin, HP on | keep → send | 110.1 | 18.8 / 37.9 | t+80.6 | **29.5 s** |

All figures are RE.

## Run 1 (2026-09-27): boot move FullyKeep → FullySend, HP off

| | stamp | t+ | value | source |
|---|---|---|---|---|
| motor start | 18:32:56.096 | 0 | | RE state KeepingLess / LOG |
| sieg-btu first post after boot (300 s snapshot) | 18:33:18.704 | 22.6 | keep 4.85 | RE |
| keep first change | 18:33:19.704 | ≤23.6 (upper bound, see caveats) | 4.80 | RE |
| send first tick / first nonzero | 18:33:33.720 / 18:33:35.079 | 37.6 / 39.0 | 0.00 / 0.04 | RE |
| keep reaches 0 | 18:34:08.712 | 72.6 | 0.00 | RE |
| send settled | 18:34:14.831 | **78.7** | 4.13 | RE |
| motor stop | 18:34:46.368 | 110.3 | | RE state FullySend / LOG |
| settled values | | | keep 0.00, send 4.14–4.23 (mean 4.17) | RE |

## Run 2 A (2026-09-28): boot move FullyKeep → FullySend, HP off

| | stamp | t+ | value | source |
|---|---|---|---|---|
| motor start | 12:41:19.231 | 0 | | LOG / RE state KeepingLess 12:41:19.230 |
| sieg-btu first post after boot (snapshot) | 12:41:41.821 | 22.6 | keep 4.85 | RE |
| keep first change | 12:41:43.821 | ≤24.6 (upper bound) | 4.79 | RE |
| send first tick / first nonzero | 12:41:57.476 / 12:41:58.388 | 38.2 / 39.2 | 0.00 / 0.04 | RE |
| keep reaches 0 | 12:42:30.826 | 71.6 | 0.00 | RE |
| send settled | 12:42:38.359 | **79.1** | 4.16 | RE |
| motor stop | 12:43:09.452 | 110.2 | | LOG / RE state FullySend |
| settled values | | | keep 0.00, send 4.15–4.25 (mean 4.19) | RE |

## Run 2 B/C: admin jog toward keep, then back to send

B: 12:43:38.218 → 12:43:44.497, 6.2 s toward keep (LOG). C: 12:43:44.519 → 12:45:34.568, 110 s toward send (LOG). No keep-leg reading was posted between 12:42:30.826 (0) and the 12:46:41.815 snapshot (0) (RE), so the 6.2 s jog moved no keep flow. The send leg drifts from 4.20 to 4.03 through C and afterwards (STRIP). That drift is slow and continues after the motor stops.

## Run 2 D: admin FullySend → FullyKeep, HP off until 12:48:50

| | stamp | t+ | value | source |
|---|---|---|---|---|
| motor start | 12:47:10.456 | 0 | | LOG / RE state KeepingMore 12:47:10.453 |
| pre-travel | | | keep 0.00 (12:46:41.815 snapshot), send 4.00–4.05 | RE |
| send first change | 12:47:28.736 | **18.3** | 3.96 (3.91 at t+21.2) | RE |
| keep first change | 12:47:40.818 | **30.4** | 0.42 (the first step from 0) | RE |
| send reaches floor | 12:48:09.808 | 59.4 | 0.03 (never posts 0; see the cadence section) | RE |
| keep last change | 12:48:36.820 | **86.4** | 5.02 | RE |
| motor stop | 12:49:00.530 | 110.1 | | LOG / RE state FullyKeep 12:49:00.527 |
| settled values | | | keep 5.02 (drifts to 5.11–5.16 by 12:56 with the HP on), send 0.03 | RE |

## Run 2 T3: admin FullyKeep → FullySend, HP on (LWT 120.9 °F at the open)

| | stamp | t+ | value | source |
|---|---|---|---|---|
| motor start | 12:57:10.069 | 0 | | LOG / RE state KeepingLess 12:57:10.067 |
| pre-travel | | | keep 5.11–5.21 (±0.05 jitter, 5.16 at 12:56:41.817), send 0.03 | RE |
| keep first change | 12:57:28.820 | **18.8** | 5.10 (5.03 at t+20.8) | RE |
| send first tick / first 0.10 | 12:57:47.934 / 12:57:49.435 | 37.9 / 39.4 | 0.03 / 0.10 | RE |
| keep reaches 0 | 12:58:22.817 | 72.7 | 0.00 | RE |
| send settled | 12:58:30.649 | **80.6** | 4.34 | RE |
| motor stop | 12:59:00.121 | 110.1 | | LOG / RE state FullySend 12:59:00.118 |
| settled values | | | keep 0.00, send 4.27–4.40 (mean 4.32) | RE |

## Findings

- In all four full travels the flow is flat 23.7–31.5 s before the 110 s motor run ends. Keep → send settles at t+78.7 to t+80.6 in three runs, with or without the HP on. Send → keep settles at t+86.4.
- Travels in the same direction repeat closely. The keep leg reaches 0 at t+71.6 to t+72.7, and the opening send leg shows its first tick at t+37.6 to t+38.2.
- The closing port moves first. Where it can be seen (D and T3, which do not start at a boot), the closing leg first changes at t+18.3 and t+18.8. The opening leg first changes at t+30.4 (keep) and t+37.6 to t+38.2 (send). The first ~18 s of motor after an end stop changes nothing, which matches taking back the 10 s overshoot plus some slack.
- The 6.2 s jog toward keep (B) does not reach that dead band.
- Send → keep is slower at the end. The send leg is at its floor by t+59.4, but the keep leg keeps rising until t+86.4, about 12 s later than the keep leg empties in the other direction.
- Total primary flow depends on valve position: about 5.0–5.2 gpm at full keep against about 4.2–4.3 gpm at full send.

## Resolution and caveats

- **sieg-btu (keep leg):** samples on a 1 s grid and posts when the change exceeds about 0.04 gpm. It also posts a 300 s snapshot. RE stamps are good to about 1 s.
- **Boot moves hide the keep leg's start.** At both boots sieg-btu stays silent until t+22.6, so "first change" there is an upper bound. The non-boot travels put the true onset near t+18.
- **sieg-send (send leg):** RE stamps are tick-derived and dense. Steps are 0.04–0.05 gpm, with ±0.05 jitter once settled; T3 jitters by ±0.07. The settle stamps therefore depend on the band chosen by a few seconds.
- The send leg's floor of 0.03 is a reporting artefact, not flow (see the cadence section in the verdict).

## Flow posting cadence against the layout (run 2, RE)

The full listing with LATE and BELOW flags is in `cadence-list-0928.txt` (from `cadence_list.py`); `cadence_check.py` gives the histograms. The window is each travel from t−30 s to stop+20 s.

| channel (layout delta) | travel | posts | posted below delta | ≥delta but >2 s apart |
|---|---|---|---|---|
| sieg-flow (10) | A | 43 | 18 (steps 4–9) | 1: 12:41:46.819 4.68 → 12:41:49.816 4.58, 3.0 s, Δ=10 exactly |
| sieg-flow (10) | D | 48 | 27 | 2: 12:46:41.815 0 → 12:47:40.818 0.42 (the onset step from 0) and 12:48:14.820 → 12:48:16.933, 2.1 s |
| sieg-flow (10) | T3 | 51 | 29 | 0 |
| sieg-send (4) | A / D / T3 | 152 / 132 / 166 | 9 / 8 / 8 (Δ=0 repeats) | 5 / 7 / 7, all on the settled plateau or before the travel starts, flipping between two tick-quantised levels (e.g. 4.34 ↔ 4.38) |

**sieg-flow (sieg-btu pico).** Posting on change works: 1 s grid, about 12 ms from pico stamp to scada arrival, and no real change is held back. The pico is not running the layout's delta of 10. More than half of its posts are for steps of 4–9, which fits a flow delta of about 4. The temperature steps are ≥20, matching both the layout and the firmware default of 20.
- **What the scada sent.** Nothing. The pico posts `async.btu.params` Version 000 without PicoBoardVariant or MicropythonVersion. The scada model requires those fields and Version 100, so it logs "malformed BtuMeter parameters" (12:41:39.481), raises a glitch ("sieg-btu pico_0d5b31 posts async.btu.params 000; the scada takes 100", broker capture) and returns an empty response (`gridworks-scada/gw_spaceheat/actors/api_btu_meter.py:208-213`). The layout values are only written into the reply after validation succeeds (`:229-240`), so the pico never receives the layout's delta of 10.
- **What the pico runs.** Its stored config, not the flash default. Current firmware defaults to 10 (`gridworks-pico/btu_meter/async_btu_main.py:23`), and current firmware posts Version 100 (`:251`). A 000 post means maple's pico runs older firmware. The old maple layout set `AsyncCaptureDeltaGpmX100=4` (`tlayouts/old_gen_maple.py:223`, commented out). The most likely story is that an earlier scada, which still accepted 000, pushed 4 and the pico has kept it. The 300 s snapshot also matches a stored CapturePeriodS of 300; the firmware default is 60 (`async_btu_main.py:21`).

**sieg-send (hall pico).** No params exchange appears in this window's log; hall picos only post params when they boot. Its batch cadence matches the layout, not the old default: batches every ~10 s while ticking and ~8 s when idle (layout PublishTicklistPeriodS=10, PublishEmptyTicklistAfterS=7; old default 60). The threshold of 4 is applied by the scada, not the pico (`api_flow_module.py:814-822`), and the steps are 4–5 as expected. Two things make it look like it does not report on change:
1. **Batch latency.** Readings arrive as 10 s tick batches. The latency from reading stamp to arrival has a median of 5.9 s, p90 10.6 s and max 11.0 s (`send-batch-arrivals-0928.txt`). The stamps are exact, but live views see the send leg up to 11 s late.
2. **It never posts zero.** When ticks stop, the exponential smoothing decays to 0.03 and stops there (12:48:09.808). On an empty ticklist the scada publishes zero only if `latest_gpm > AsyncCaptureThresholdGpmTimes100/100` (`api_flow_module.py:636-639`), and 0.03 is not above 0.04. So `sieg-send` reads 0.03 for the whole of full keep, and the 300 s re-posts at 12:50:14.668 and 12:55:14.610 repeat 0.03. This is a real defect on a metering path.
