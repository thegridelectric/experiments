# maple 4d window, 2026-09-27

What this is: a read-only analysis of the maple beta field window (scada `jm/spruce-unlimbo` @ 92b4e5d1, laptop 18:34–18:45 ET). All times below are **box time** (laptop ≈ box + 69 s). Sources are under `scratch/`: `maple-window-20260927-184556.log` (primary, "P:<line>"), `maple2-window-20260927-184606.log` (scada2, "S2:<line>"), `maple-events-20260927-184611/` (the two report.event files), and `broker-capture-20260927-183402.jsonl` ("cap #n", CapturedUnixMs is laptop time).

## Verdict

**4d verifies.** `sieg-send-flow` and `primary-flow` report through the whole window. They start from the first `sieg-send` post (synced 18:32:58.196, then `channel.readings` every ~11 s from 18:33:42.206 to 18:43:47.247), and the derived generator consumes those lists (for example P: 18:36:16.275 IN `sieg-send/to/derived-generator/channel.readings`, followed by 10 `single.reading` OUT). After the flow went nonzero, the sieg-send-flow age on the strip stayed between 1 s and 20 s. On every one of the 22 valued strip lines, primary-flow equals sieg-flow + sieg-send-flow within 0.01 gpm. The same holds for all 449 primary-flow readings in the two report.events (183 + 266, 0 mismatches), and `sieg-send-flow` matches `sieg-send` exactly in values and timestamps (identity). The valve travelled from FullyKeep (StartKeepingLess 18:32:56.096) to FullySend (ResetToFullySend 18:34:46.368) in 110.27 s ("Motor stopped after 110.0 s"). During the travel the flow visibly moved from the keep leg to the send leg: sieg-flow 4.85→0.00 gpm between 18:33:18.704 and 18:34:08.712, and sieg-send 0.00→4.13 gpm between 18:33:33.720 and ~18:34:15. The 4ci boot posture also holds: all four direct bosses commanded their relays within 3 s of boot, every command was acked, and there was no relay_silent or relay_nack. There were no Tracebacks or ERRORs. Items outside 4d are worth a look: `transactive-power` has no value all window; zone heat-calls go stale for ~3 min in each 5-min cycle; and six `params-version` Warning glitches at boot come from older pico firmware, not PicoMissing. Report.event lists are not time-ordered: primary-flow steps back up to 10.8 s where the sieg-btu and sieg-send batches interleave.

## 1. sieg-view strip (all 24 lines)

`*` = derived. Check = |sieg-flow + sieg-send-flow − primary-flow| ≤ 0.01 gpm.

| P line | box time | valve | sieg-flow | sieg-send-flow* | primary-flow* | check |
|---|---|---|---|---|---|---|
| 503 | 18:32:55.988 | FullyKeep | -- | -- | -- | n/a (no values) |
| 834 | 18:32:56.096 | KeepingLess | -- | -- | -- | n/a (no values) |
| 3170 | 18:33:25.991 | KeepingLess | 4.61gpm@0s | 0.00gpm@28s | 4.61gpm@0s | ok |
| 4997 | 18:33:55.992 | KeepingLess | 2.29gpm@0s | 1.56gpm@3s | 3.85gpm@0s | ok |
| 7170 | 18:34:25.995 | KeepingLess | 0.00gpm@17s | 4.13gpm@11s | 4.13gpm@11s | ok |
| 7684 | 18:34:46.370 | FullySend | 0.00gpm@38s | 4.18gpm@11s | 4.18gpm@11s | ok |
| 8049 | 18:34:55.997 | FullySend | 0.00gpm@47s | 4.17gpm@9s | 4.17gpm@9s | ok |
| 9915 | 18:35:25.999 | FullySend | 0.00gpm@77s | 4.18gpm@5s | 4.18gpm@5s | ok |
| 10987 | 18:35:56.001 | FullySend | 0.00gpm@107s | 4.20gpm@4s | 4.20gpm@4s | ok |
| 11906 | 18:36:26.003 | FullySend | 0.00gpm@137s | 4.20gpm@20s | 4.20gpm@20s | ok |
| 12915 | 18:36:56.006 | FullySend | 0.00gpm@167s | 4.22gpm@9s | 4.22gpm@9s | ok |
| 14410 | 18:37:26.010 | FullySend | 0.00gpm@197s | 4.24gpm@4s | 4.24gpm@4s | ok |
| 15490 | 18:37:56.012 | FullySend | 0.00gpm@227s | 4.21gpm@7s | 4.21gpm@7s | ok |
| 16930 | 18:38:26.015 | FullySend | 0.00gpm@7s | 4.22gpm@10s | 4.22gpm@7s | ok |
| 18156 | 18:38:56.016 | FullySend | 0.00gpm@37s | 4.22gpm@10s | 4.22gpm@10s | ok |
| 19472 | 18:39:26.018 | FullySend | 0.00gpm@67s | 4.24gpm@4s | 4.24gpm@4s | ok |
| 20817 | 18:39:56.021 | FullySend | 0.00gpm@97s | 4.22gpm@11s | 4.22gpm@11s | ok |
| 23244 | 18:40:26.038 | FullySend | 0.00gpm@127s | 4.25gpm@10s | 4.25gpm@10s | ok |
| 24838 | 18:40:56.039 | FullySend | 0.00gpm@157s | 4.26gpm@5s | 4.26gpm@5s | ok |
| 26584 | 18:41:26.041 | FullySend | 0.00gpm@187s | 4.28gpm@3s | 4.28gpm@3s | ok |
| 27804 | 18:41:56.044 | FullySend | 0.00gpm@217s | 4.32gpm@11s | 4.32gpm@11s | ok |
| 29521 | 18:42:26.048 | FullySend | 0.00gpm@247s | 4.35gpm@7s | 4.35gpm@7s | ok |
| 30733 | 18:42:56.049 | FullySend | 0.00gpm@277s | 4.32gpm@4s | 4.32gpm@4s | ok |
| 31959 | 18:43:26.052 | FullySend | 0.00gpm@7s | 4.35gpm@1s | 4.35gpm@1s | ok |

- The arithmetic holds on every valued line; no line fails. Where the ages differ, primary-flow takes the timestamp of the addend that triggered it. For example, at 18:34:25.995 primary-flow is `@11s`, which matches sieg-send-flow, while sieg-flow is `@17s`. At 18:38:26.015 primary-flow is `@7s`, which matches the fresh sieg-flow reading of 18:38:18.699, while sieg-send-flow is `@10s`. Neither case is a stale addend: the other addend's value was unchanged.
- **First move:** P:832 18:32:56.096 `StartKeepingLess: FullyKeep -> KeepingLess` (P:835 "Motor toward send for 110 s from keep_seconds 100").
- **FullySend:** P:7682 18:34:46.368 `ResetToFullySend: KeepingLess -> FullySend`; P:7685 "Motor stopped after 110.0 s: keep_seconds 0". **Travel = 110.27 s.**
- The first `sieg-send` synced post (18:32:58.196) produced sieg-send-flow = 0 before sieg-flow had any value. Primary-flow therefore first appears at 18:33:18.704, with the first sieg-flow reading.

## 2. Vanishing / aging readings and blind reasons

No strip line carries a `blind` reason. The only "blind" in the log is LocalControl's own message: P:2340 18:33:13.147 `[lc] Blind since 12 seconds`, right after P:2339 "Buffer Temps Available: False". That is a boot effect: all tank depths were still in the "no value" list at P:2306 18:33:11.092, and the list was clear by 18:33:26.094.

Capture periods are not in layout-lite, so the "period" column is inferred from the observed cadence of each channel.

| channel | time (box) | what | cause traced |
|---|---|---|---|
| sieg-flow | boot → 18:33:18.704 | no value (`--` on strip at 18:32:55.988, 18:32:56.096) | Boot. pico-cycler power-cycled the picos: P:2053 18:32:58.989 "OpenRelay to vdc-relay", P:2206 18:33:04.018 "CloseRelay". sieg-btu's first post was 18:33:18.706 |
| sieg-flow | 18:34:25 @17s → 18:37:56 @227s; reset 18:38:26 @7s; → 18:42:56 @277s; reset 18:43:26 @7s | age climbs while value 0.00 | Channel absent from a live pico's posts. sieg-btu kept posting SyncedReadings (e.g. 18:35:05.700, 18:35:34.700, 18:36:15.705). sieg-flow sat at 0 in FullySend and was posted only at 18:34:08.712, 18:38:18.699 and ~18:43:19, a ~300 s cadence. It never exceeds that period (max 277 s) |
| sieg-send-flow | 18:33:25.991 `0.00gpm@28s` | aged while pico alive | The pico was alive and posting `ticklist.hall` at 18:33:15.406, 18:33:23.344 and 18:33:31.168, but no reading came out because flow was 0, below AsyncCaptureThresholdGpmTimes100 = 4. The next post was 18:33:42.206. Expected |
| sieg-send-flow | 18:36:26.003 `@20s` | age twice the ~11 s post cadence | Batch latency. The 18:36:16.266 post's newest sample was 18:36:06.440 (report.event; the largest sieg-send gap in that slot is 9.9 s, 18:36:06.440→18:36:16.361). Not a fault |
| hp-odu-pwr, hp-idu-pwr | @300s at 18:37:56.012 and 18:42:56.049; @30s / @29s on the next line | age reaches the period | power-meter posts every 300 s (readings 18:32:56.173, 18:37:56.212 in report.event). Equals the period and does not exceed it |
| dist-swt, dist-rwt | dist-rwt @271s at 18:42:26.048 → @1s at 18:42:56.049 | age climbs | analog-temp (on scada2) posts only changed channels. The ~300 s cadence is consistent with a periodic post. Scada2's analog-temp was alive throughout (245 posts) |
| zone1/zone2 heat-call | `stale` from 18:35:11.108–18:37:56.131 and 18:40:11.151–18:42:56.175 (UnknownChannels) | stale ~3 min per 5-min cycle | P:15513 18:37:56.216 `[HeatCall periodic] zone1-living-rm-heat-call now=1790548676.2 next=1790548500 period=300`, which is 176 s overdue; the same at P:30818 18:42:56.573 (`next=1790548800`). The periodic emission fires only when a whitewire-pwr reading arrives from power-meter, which posts every 300 s (inference; not traced in code) |
| transactive-power | every UnknownChannels line, 18:32:56.089 → 18:43:41.182 | never has a value; absent from both report.events | No cause found in the log. It is a power-meter derived channel (OnTrigger, inputs hp-odu-pwr and hp-idu-pwr), and both inputs had values |
| required-energy | no value until 18:34:59.048 (listed through 18:34:56.107, clear at 18:35:11.108) | late first value | No cause found. Periodic, EmitPeriodS 60 |
| dist-flow (not on strip) | PicoMissing 18:33:13.496 (P:2383) | boot PicoMissing | Boot power-cycle. First post 18:33:17.425. After that the pico posted synced readings only at 18:34:59.060 and 18:40:14.658 (zero flow; the gap is 315.6 s), so dist-flow is absent from the 18:35–18:40 report.event. sieg-send's synced posts fall at the same instants (18:34:59.062, 18:40:14.660) |

Data ordering (not a 4d defect): report.event lists are in arrival order, not time order. sieg-send steps back from 18:34:59.061 to 18:34:48.283, because the synced post was handled before the channel.readings batch. primary-flow steps back 5 times in the first report (−8.0, −9.4, −10.4, −4.4, −10.8 s) and once in the second (−1.4 s at 18:38:18.699 → 18:38:17.299), because sieg-btu and sieg-send batches interleave.

## 3. Glitches

All payloads come from the broker capture (Payload TypeName `glitch`). Box time is CreatedMs.

| cap # | box time | Node | Type | Summary | Details |
|---|---|---|---|---|---|
| 0 | 18:32:56.089 | s | Warning | disabled-roster | `nodes: - \| channels: primary-pump-pwr` |
| 8 | 18:33:07.289 | buffer | Warning | params-version | `buffer pico_8f5530 posts tank.module.params 110; the scada takes 200` |
| 9 | 18:33:07.945 | tank1 | Warning | params-version | `tank1 pico_8a2a21 posts tank.module.params 110; the scada takes 200` |
| 10 | 18:33:08.554 | tank2 | Warning | params-version | `tank2 pico_219530 posts tank.module.params 110; the scada takes 200` |
| 11 | 18:33:11.361 | tank3 | Warning | params-version | `tank3 pico_219430 posts tank.module.params 110; the scada takes 200` |
| 12 | 18:33:15.794 | store-btu | Warning | params-version | `store-btu pico_18a132 posts async.btu.params 000; the scada takes 100` |
| 13 | 18:33:16.363 | sieg-btu | Warning | params-version | `sieg-btu pico_0d5b31 posts async.btu.params 000; the scada takes 100` |

- The six boot glitches are **not the PicoMissing kind**. They are a firmware params-version mismatch, raised on each pico's first params post after the boot power-cycle. For the two BTU picos the log also shows the pydantic rejection: P:2509 18:33:15.794 `[store-btu] malformed BtuMeter parameters: 3 validation errors for AsyncBtuParams` (PicoBoardVariant missing, MicropythonVersion missing, `Input should be '100' ... input_value='000'`), and the same at P:2526 18:33:16.363 for sieg-btu. Readings flowed anyway: tank depths were populated by 18:33:26 and sieg-btu readings arrived from 18:33:18.706. Nothing in `scratch/basic-sieg/` mentions params-version.
- The one PicoMissing (dist-flow, 18:33:13.496) went to pico-cycler only and did not raise a glitch.
- There were **no later glitches**. The log has 7 glitch OUT lines, the last at 18:33:16.366, and the broker capture holds exactly those 7.

## 4. Relay boot posture (4ci)

Boot started at 18:32:55.66. Every command below was sent in the first 3.4 s, and each was followed by a `gw.dispatch.ack` from the relay.

| box time | P line | commander | command → relay | ack |
|---|---|---|---|---|
| 18:32:55.978 | 349 | hp-boss | OpenRelay → **hp-scada-ops-relay** | 18:32:56.014 |
| 18:32:56.022 | 605 | lc | DischargeStore → **charge-discharge-relay** | 18:32:56.052 |
| 18:32:56.023 | 607 | lc | OpenRelay → store-pump-relay | 18:32:56.054 |
| 18:32:56.023 | 609 | lc | CloseRelay → tstat-common-relay | 18:32:56.056 |
| 18:32:56.024 | 611 | lc | SwitchToWallThermostat → zone1-living-rm-failsafe-relay | 18:32:56.057 |
| 18:32:56.025 | 613 | lc | OpenRelay → zone1-living-rm-ops-relay | 18:32:56.059 |
| 18:32:56.025 | 615 | lc | SwitchToWallThermostat → zone2-bedroom-failsafe-relay | 18:32:56.061 |
| 18:32:56.026 | 617 | lc | OpenRelay → zone2-bedroom-ops-relay | 18:32:56.063 |
| 18:32:56.027 | 620 | lc | SwitchToScada → hp-failsafe-relay | 18:32:56.065 |
| 18:32:56.028 | 622 | lc | SwitchToScada → aquastat-ctrl-relay | 18:32:56.067 |
| 18:32:56.094 | 829 | sieg-loop | SendMore → hp-loop-keep-send-relay | 18:32:56.101 |
| 18:32:56.095 | 831 | sieg-loop | CloseRelay → hp-loop-on-off-relay | 18:32:56.103 |
| 18:32:58.989 | 2053 | pico-cycler | OpenRelay → vdc-relay ("TRIGGERING PICO REBOOT! startup") | 18:32:58.994 |
| 18:33:04.018 | 2206 | pico-cycler | CloseRelay → vdc-relay | 18:33:04.028 |

lc also sent AnalogDispatch 35 to store-010v and dist-010v at 18:32:56.029–030, and both were acked. relay_silent: 0; relay_nack: 0.

fsm.full.report lines for the sieg-loop move:
- Start: hp-loop-keep-send-relay → sieg-loop 18:32:56.335; hp-loop-on-off-relay → sieg-loop 18:32:56.337.
- Stop: P:7681 18:34:46.367 "sending OpenRelay to HpLoopOnOff"; hp-loop-on-off-relay → sieg-loop 18:34:46.391; sieg-loop → s 18:34:46.401.

The move completed.

## 5. report.event contents

| file (box) | slot | channels | sieg-flow | sieg-send | sieg-send-hz | sieg-send-flow | primary-flow |
|---|---|---|---|---|---|---|---|
| 22:35:00Z | 18:30:00–18:35:00 | 86 | 41 (18:33:18.704–18:34:08.712, every 1–2 s) | 143 (18:32:58.195–18:34:58.592) | 143 | 143 | 183 |
| 22:40:00Z | 18:35:00–18:40:00 | 84 | 1 (18:38:18.699, value 0) | 265 (18:34:59.352–18:39:56.057) | 265 | 265 | 266 |

- **Cadence.** sieg-send, sieg-send-hz and sieg-send-flow share identical timestamps, with samples 0.1–12 s apart that arrive in ~11 s batches. The first gap in report 1 is 35.5 s (zero flow at boot). Primary-flow = sieg-send-flow timestamps ∪ sieg-flow timestamps (183 = 142 + 41 in report 1; 266 = 265 + 1 in report 2). Values are GpmTimes100.
- **Channel names**, report 1: hp-odu-pwr, hp-idu-pwr, dist-pump-pwr, store-pump-pwr, oil-boiler-pwr, zone1/zone2 whitewire-pwr, temp, set; 13 relays; buffer/tank1–3 depth1–3 device and micro-v; dist-010v, store-010v, sieg-flow, sieg-hot, sieg-cold, store-flow, store-hot-pipe, store-cold-pipe, dist-flow, dist-flow-hz, sieg-send, sieg-send-hz, dist-swt, dist-rwt, hp-lwt, hp-ewt, buffer-hot-pipe, buffer-cold-pipe, oat, zone1-living-rm-gw-temp, sieg-send-flow, primary-flow, usable-energy, required-energy, zone1/zone2 heat-call, buffer/tank1–3 depth1–3.
- Report 2 is the same list without dist-flow and dist-flow-hz. **transactive-power** is absent from both.
- **StateList**, report 1 (29 machines): ltn.la, auto.five-v-boss, buffer, tank1, tank2, tank3, sieg-btu, store-btu, dist-flow, sieg-send, auto.lc, auto.lc.n.hp-boss, auto.lc.n.sieg-loop, auto.lc.n.hp-boss.hp-scada-ops-relay, auto.lc.n.charge-discharge-relay, auto.lc.n.store-pump-relay, auto.lc.n.tstat-common-relay, auto.lc.n.zone1-living-rm-failsafe-relay, auto.lc.n.zone1-living-rm-ops-relay, auto.lc.n.zone2-bedroom-failsafe-relay, auto.lc.n.zone2-bedroom-ops-relay, auto.lc.n.hp-failsafe-relay, auto.lc.n.aquastat-ctrl-relay, auto.lc.n.sieg-loop.hp-loop-keep-send-relay, auto.lc.n.sieg-loop.hp-loop-on-off-relay, auto.five-v-boss.pico-cycler, auto.five-v-boss.pico-cycler.vdc-relay, s, auto.
- **StateList**, report 2 (26 machines): adds auto.lc.n. It drops ltn.la, auto.five-v-boss, auto.lc and auto.lc.n.sieg-loop, because there were no transitions in that slot. FsmReportList sizes are 12 and 3.

## 6. Traceback / ERROR / Unknown / unexpected

| log | Traceback | ERROR | "Unknown" | "unexpected" | other |
|---|---|---|---|---|---|
| primary | 0 | 0 | 44, all `[UnknownChannels]`. First two: P:826 18:32:56.089 (boot, all channels no value) and P:2306 18:33:11.092 (tank depths, sieg/store/dist flow, primary-flow no value) | 0 | 2 `malformed BtuMeter parameters` pydantic blocks: P:2509 18:33:15.794 store-btu, P:2526 18:33:16.363 sieg-btu (the 10 lower-case "error" lines all belong to these). No WARNING or CRITICAL lines |
| scada2 | 0 | 0 | 0 | 0 | none |

After 18:35:11 the UnknownChannels lines list only `transactive-power`, plus the stale heat-calls in the windows noted in item 2.

## 7. scada2

- **Boot.** The log starts at 18:32:55.548. local_mqtt reached `active` at S2:404 18:32:56.101, and the primary saw scada2 peer.active at 18:32:56.114 (event file).
- **One blip.** S2:529 18:33:00.964 `active -- response_timeout --> awaiting_peer`, back to `active` at S2:539 18:33:00.974 (10 ms). The unacked message was scada2's boot Ping `cf844c9c` (S2:376, 18:32:55.958). It was sent before the primary's own local_mqtt had subscribed (primary suback 18:32:56.107, P:999), so the ping was lost and the ack timed out 5 s later. This is a benign boot race. The primary logged `gridworks.event.comm.response.timeout` at P:2146 18:33:00.994 plus a fresh peer.active.
- **After the blip.** There were no further link transitions. Scada2 made 274 mqtt OUTs (245 analog-temp synced-readings, 5 each from zone1/zone2-stat, 19 own). The last was at 18:43:49.432 before "window done (scada2)". There were no errors or Unknowns.
