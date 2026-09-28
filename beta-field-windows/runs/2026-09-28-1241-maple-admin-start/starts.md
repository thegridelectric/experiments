# HP start, maple 2026-09-28 12:52 (one row for the starts table)

Status: Draft · Pass 0 · Updated 2026-09-28

Heat pump start during the 09-28 window, with the sieg valve held at FullyKeep. Times are box ET. Temperatures are °F, converted from CelsiusX100; depth channels are FahrenheitX100.
Sources: **RE** = report.event (`maple-events-20260928-130239/`, readings through 13:00:00), **LOG** = `maple-window-20260928-130220.log`, **STRIP** = `sieg-view` line with age.
Script: `start_row.py` over `start-dump-0928.txt`.

| field | value | source |
|---|---|---|
| HP commanded on | 12:48:50.264 admin.hp-boss HpOn; hp-scada-ops-relay closed at 12:48:50.302 | RE state |
| first hp-odu-pwr > 300 W | 12:52:25.312, 378 W | RE |
| compressor start (first ≥ 1500 W) | 12:55:44.281, 1665 W. Power posts in ~300 W steps: 378 → 756 → 1056 → 1180 → 1665 W | RE |
| valve posture held | FullyKeep from 12:49:00.527 until the open | RE state / LOG |
| destination | Store was commanded, but no water went to the store: store-pump-relay RelayOpen throughout, store-pump-pwr 0 W, store-flow 0. At full keep the HP recirculates through the keep leg, so this was a closed run | RE |
| store-hot-pipe at compressor start | 64.0 (12:55:17.959). At the >300 W point: 63.2 (12:51:41.953) | RE |
| store depths at compressor start | tank1 81.3 / 75.5 (depth1 / depth3), tank2 66.3 / 59.0, tank3 60.6 / 60.1 (12:55:36–40) | RE |
| buffer depths at compressor start | 114.3 / 111.5 / 76.2 (depth1 / 2 / 3, 12:55:36–37) | RE |
| hp-lwt / hp-ewt at compressor start | 98.4 / 97.1 (12:55:43.429) | RE |
| hp-lwt / hp-ewt / sieg-hot at the open (12:57:10.069) | 120.9 (12:57:09.261) / 117.6 (12:57:08.660) / 107.5 (12:57:09.817); lift 3.3 | RE, matches STRIP |
| LWT slope, closed run | **16.0 °F/min**, linear fit over 24 readings from compressor start to the open. From the >300 W point it is 12.5 °F/min (64 readings; LWT first moves at 12:52:51.338, 62.3) | RE |
| EWT rise, first 2 min after compressor start | 97.1 → 126.0 at 12:57:39.275, +28.9 °F in 116 s. The open falls inside this window at +86 s (EWT 117.6, +20.5) | RE |
| peak hp-lwt | **133.9 at 12:58:00.498**, 50 s after the open | RE |
| EWT dip | No single reading falls more than 5 °F below the one before it. The pico posts ~1 °F steps every 0.6–1 s, and the largest single drop is 1.17 °F, so that criterion never fires. EWT peaks at 126.0 (12:57:39.275, lift 3.3). The first reading more than 5 °F below that peak is **120.4 at 12:58:02.503, lift 13.5** (LWT 133.9). The bottom is 69.9 at 12:59:38.959 (lift 22.0, LWT 91.9) | RE |
| dip timing vs valve | The keep flow starts falling at 12:57:28.8 (open +18.8 s). EWT turns over at +29 s, before the send leg's first tick at +37.9 s | RE |
| buffer-hot-pipe before the open | 103.4 (last post 12:53:35.546; STRIP 103.4 @215 s at 12:57:10) | RE / STRIP |
| buffer depths before the open | 114.3 / 111.5 / 76.2 (12:56:36.257) | RE |
| buffer-hot-pipe 3 min after the open | 91.3 at about 13:00:16 (STRIP 91.3 @3 s at 13:00:19.219). Last RE is 94.1 at 12:59:56.753 | STRIP / RE |
| buffer depths ~3 min after the open | 115.2 (12:59:38.571) / 111.4 (12:59:36.245) / 78.5 (12:59:56.198). The RE data ends at 13:00:00, so these are open +2.5–2.8 min, not +3 | RE |
| how the start ended | Admin MoveToFullSend at 12:57:10.062 (LOG). Motor ran 12:57:10.069 → 12:59:00.121. The HP stayed on (ops relay closed through 12:59:58). hp-odu-pwr peaked at 4126 W (12:57:30.421), then fell to 2538 W by 12:59:07.329. LWT fell to 90.0 by 12:59:53.166 | LOG / RE |

Notes: the only thing that took heat out of the loop before the open was its own water mass, which is why LWT climbed 16 °F/min with a lift of only 3.3 °F. After the open, LWT kept rising for 50 s (to 133.9) while EWT started falling. The cold send-side water reached the HP inlet about 30 s after the motor started.
