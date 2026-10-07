# HP start, maple 2026-09-28 13:24 (admin start, admin-hold timeout)

Status: Draft · Pass 0 · Updated 2026-09-28

Heat pump start during the 13:14 maple window, with the sieg valve held at FullyKeep. The admin hold timed out mid-start, local control turned the HP off, and the valve opened to send. Times are box ET. Temperatures are °F, converted from CelsiusX100; depth channels are FahrenheitX100.
Sources: **RI** = folded readings `instances/maple-gw.readings-000.json` (to 13:30:00), **RE** = report.event StateList / FsmReportList, **LOG** = `maple-window-20260928-133008.log.gz`. Run folder: `experiments/beta-field-windows/runs/2026-09-28-1314-maple-admin-start-timeout/`.
Script: `scratch/basic-sieg/start_row_run3.py` over `run3-start.txt`, which comes from `run3_dump.py`.

| field | value | source |
|---|---|---|
| HP commanded on | 13:20:15.253 AdminDispatch TurnOn; admin.hp-boss HpOn at 13:20:15.261; hp-scada-ops-relay closed at 13:20:15.303 | LOG / RE |
| first hp-odu-pwr > 300 W | 13:23:50.708, 354 W (3 min 35 s after the call) | RI |
| compressor start (first ≥ 1500 W) | 13:25:00.717, 1624 W. The post before it is 1488 W at 13:24:11.712, and the power channel posts in ~300 W steps, so the crossing lies between those two stamps | RI |
| valve posture held | FullyKeep from 13:18:09.794 until the open at 13:25:27.608 | LOG |
| destination | None: a closed run. The store pump was off throughout (store-pump-relay RelayOpen, store-pump-pwr 0, store-flow 0) and charge-discharge-relay stayed DischargingStore. Local control was Dormant under admin, then went to HpOffStoreOff at 13:25:15.434 | RI / RE / LOG |
| store-hot-pipe at compressor start | 97.6 (13:24:49.954) | RI |
| store depths at compressor start | tank1 80.5 / 75.7 (depth1 / depth3), tank2 66.6 / 59.1, tank3 60.7 / 60.1 (13:24:44–49) | RI |
| buffer depths at compressor start | 109.4 / 109.4 / 105.5 (depth1 / 2 / 3, 13:24:49.488) | RI |
| hp-lwt / hp-ewt / sieg-hot at compressor start | 112.8 (13:25:00.503) / 111.0 (13:24:57.502) / 100.9 (13:24:59.743). This was a warm start: the loop was already at ~105 | RI |
| HP commanded off by local control | 13:25:15.486 TurnOff; ops relay opened at 13:25:15.664. LWT was 114.7 and EWT 112.9 | RE / RI |
| hp-lwt / hp-ewt / sieg-hot at the open (13:25:27.608) | 116.5 (13:25:23.917) / 115.7 (13:25:27.319) / 104.2 (13:25:26.747); lift 0.8 | RI |
| LWT slope, closed run | **10.3 °F/min**, linear fit over 12 readings from the first LWT rise (13:24:26.683, 106.3) to the open. From first rise to the relay opening it is 10.7 °F/min (10 readings). Over the 27 s from ≥1500 W to the open it is 9.2 °F/min (4 readings only) | RI |
| EWT, first 2 min after compressor start | 111.0 → peak 119.4 at 13:25:52.133 → 106.1 at 13:26:50.150. The open falls at +27 s | RI |
| peak hp-lwt | **123.9 at 13:26:20.948**, 53 s after the open and 65 s after the HP was commanded off | RI |
| EWT dip | No single reading falls more than 5 °F below the one before it; the largest single drop is 0.99. The first reading more than 5 °F below the EWT peak is **113.6 at 13:26:32.756, lift 10.3** (LWT 123.9). hp-ewt's last post in the file is 106.1 at 13:26:50.150 (lift 16.0) | RI |
| buffer before the open | buffer-hot-pipe 105.4 (13:23:02.036); depths 109.4 / 109.4 / 105.5 | RI |
| buffer ~3 min after the open | buffer-hot-pipe 116.3 (13:28:11.395); depths 112.2 (13:28:22.906) / 109.4 (13:27:49.478) / 106.2 (13:28:11.151) | RI |
| how the start ended | The admin hold timed out at 13:25:15.359 ("Admin timed out! Auto"). Local control woke into HpOffStoreOff and sent TurnOff to hp-boss, and the ops relay opened at 13:25:15.664. The sieg-loop took the tree at 13:25:27.594 and started a move to send. Admin re-closed the relay at 13:26:33.114, after 77.5 s open. Power peaked at 2318 W (13:27:09.751), then fell 1266 W → 75 W at 13:27:56.762 → 13:27:57.765, which is 162 s after the relay opened. Admin TurnOff followed at 13:28:26.870, after the stop | LOG / RE / RI |
