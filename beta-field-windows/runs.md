# Runs

One line per field window, newest first. The run folder holds the evidence;
the verdict here is one clause.

| Run | House | Scada | Strategy | Label | Starts | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `2026-09-28-1314-maple-admin-start-timeout` | maple | eae6078e | HoldFullSend, admin-driven | second closed start; admin hold timed out and the loop opened itself | 1 | warm closed start, slope 10.3 F/min, opened by the admin-lease timeout at 116.5 F, peak 123.9 F; the lapse let local control turn the heat pump off at 13:25:15 and the Ecodan ran down 162 s later; `starts.md` |
| `2026-09-28-1241-maple-admin-start` | maple | eae6078e | HoldFullSend, admin-driven | first Ecodan start held at full keep, opened by hand | 1 | LWT 61→134 F closed in ~5 min (11–15 F/min), opened at 120.9 F, peak 133.9 F; see `starts.md` |
| `../2026-09-28-maple-ecodan-start-in-full-keep/` (own folder) | maple | b9679d4e | HoldFullSend, admin-driven | Ecodan called at full keep with 69 F inlet | 1 | power at 3 min 52 s, 1.5 kW at 6 min; kept loop climbed 56 F in 4 min; its README |
| (folder top, round five) | maple | 92b4e5d1 | HoldFullSend | 4d sieg-send verification | 0 | 4d verifies; `maple-4d-window-analysis.md` |
