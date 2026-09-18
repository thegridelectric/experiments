# gwalert-no-data-page, 2026-09-16

> What this is: does stopping the deployed spruce scada page Opsgenie
> through gwalert's no-data check, on the live fleet with real timing?
> PASS, 14.7 minutes from stop to page; verdict in Found, the logbook
> entry is the index record.

## Why

On 2026-09-15 the spruce scada was down from 16:14 to 17:21 ET (the pico
update window) and nobody was paged. Reading the alerts box journal
showed gwalert did post at 16:20 ET and Opsgenie accepted it; the post
folded into that morning's `2026-09-15-spruce-no_data` alert, which was
acknowledged and still open. Opsgenie de-duplicates by alias while an
alert is open, and a de-duplicated post notifies nobody. That is the
intended behavior of the per-day alias; what remained unproven was the
whole path on the day it matters: scada stops, gwalert notices inside
its window, Opsgenie creates an alert and a phone rings. The `[ALERT]`
journal line also gained the house name and the Opsgenie alias in the
same change (gridworks-alerts `e3e9b47`), so the log under test is the
one a future reader reconstructs an outage from.

## Setup

- Detector: gwalert on the alerts box (`alerts.electricity.works`),
  gridworks-alerts `e3e9b47` (PR #10, merge `9d89666`), service
  restarted 18:04:32Z, 5-minute cycle, 10-minute no-data threshold.
- House: spruce, gridworks-scada `02702522` on `actual-spruce`,
  deployed as `gwspaceheat` with the `gwspaceheat-restart.timer`
  watchdog. The winter hack service was not touched.
- Opsgenie: the team responder gwalert is configured with; no open
  spruce alert existed for 2026-09-16 before the run (checked by the
  API list of open alerts), so the alias was free to page.
- Driven by hand over ssh with the commands `run.sh` now holds; the
  scada was down 14 minutes 55 seconds.

## Protocol

1. Pre-flight: no open `2026-09-16-spruce-no_data` alert in Opsgenie
   (it would swallow the page); the restart timer stops with the
   service (or the watchdog undoes the window); mid-September, no heat
   call at risk for 15 minutes.
2. `sudo systemctl stop gwspaceheat gwspaceheat-restart.timer` on spruce;
   note the wall clock.
3. Poll the alerts box journal every 30 s for `[ALERT] spruce`.
4. On the alert line: read the alert back from the Opsgenie API.
5. `sudo systemctl start gwspaceheat gwspaceheat-restart.timer`; poll
   the journal until spruce reports fresh data.
6. Capture the three evidence files; emit the run instance.

## Found

**PASS** (2026-09-16). Stop to page: 14 min 44 s. Stop to Opsgenie
alert created: 14 min 44 s. Restart to gwalert seeing fresh data: 4 min
57 s.

- The alerts journal carries the new one-line form:
  `[ALERT] spruce: No data coming in since 15.0 minutes` followed by
  `Opsgenie accepted alert 2026-09-16-spruce-no_data`.
- Opsgenie created the alert at 18:19:58.3Z, P1, count 1, alias
  `2026-09-16-spruce-no_data`, message
  `[Spruce] No data coming in since 15.0 minutes`; it paged, and was
  closed from the phone 36 s later (`report.closeTime` 36084 ms).
- The cycle before the page saw spruce at 9.9 minutes, just under the
  threshold, so the page came one full cycle later than the minimum.
  Worst case from data stop to page is threshold plus one cycle plus
  the scada's own report cadence, about 15 minutes here.
- Nothing else paged; the other four houses reported on schedule
  throughout.

## Timeline

All times ET, 2026-09-16.

- 14:05:14 `systemctl stop gwspaceheat gwspaceheat-restart.timer` on
  spruce; `Deactivated successfully` at 14:05:15.
- 14:09:43 gwalert: spruce data 4.7 minutes old.
- 14:14:50 gwalert: spruce data 9.9 minutes old (under threshold).
- 14:19:57 gwalert: `[ALERT] spruce: No data coming in since 15.0 minutes`.
- 14:19:58 Opsgenie alert created (18:19:58.3Z).
- 14:20:10 `systemctl start gwspaceheat gwspaceheat-restart.timer`;
  `Started gwspaceheat.service`.
- 14:20:34 the Opsgenie alert closed by the on-call from the page.
- 14:25:07 gwalert: spruce data 0.1 minutes old.

## Analysis notes

- gwalert emits no sema word; the alert record lives in Opsgenie and
  in the journal, so this folder's alert evidence is external. The word
  that retires that is `gw.alert` (staging), which gwalerter emits and
  gwalert never will.
- `instances/gw.experiment.run-000.json` carries `HostGNodeAlias`
  `hw1.alerts`: the alerts box has no registered GNode, and the alias
  follows the rule that a cloud service hangs directly under the
  universe root, as `d1.alerts` does for the dev alerter.
- Box clocks differ: the alerts box logs UTC, spruce logs ET; the
  evidence files keep each box's own stamps and their headers say
  which.
- The 09:55 ET alert of 2026-09-15 that absorbed the evening post was
  read from the same Opsgenie list (count 2, acknowledged, open). That
  read is in the session, not in this folder; the Opsgenie history
  keeps it.

## Folder contents & experimental method

All data here is EXTERNAL EVIDENCE captured read-only after the run:
two journald slices and one Opsgenie API response. Nothing came from
the journal DB or S3, and a re-run produces a new dataset. The
experiment touched the running system: the deployed spruce scada and
its restart timer were stopped for 14 min 55 s.

- `README.md`: this record.
- `run.sh`: the runbook, the exact commands the hand-driven run used:
  stop, poll, read back, restart, capture. Stops a live house's scada;
  run it knowingly.
- `emit_instances.py`: builds `instances/gw.experiment.run-000.json`
  from the two journal slices through the sema snapshot (start = the
  `Stopping` line on spruce, end = the first fresh-data line on the
  alerts box after the restart).
- `evidence/alerts-journal.log`: gwalert's journal 18:00 to 18:30Z.
  EXTERNAL EVIDENCE (journald).
- `evidence/spruce-journal.log`: the systemd stop and start lines for
  `gwspaceheat`. EXTERNAL EVIDENCE (journald).
- `evidence/opsgenie-alert.txt`: the alert as the Opsgenie API returns
  it, closed. EXTERNAL EVIDENCE (point-in-time API response).
- `instances/gw.experiment.run-000.json`: the run's window and code
  ref, a sema instance.

Regenerate from scratch (stops the spruce scada for about 15 minutes):

    cd ~/GridWorks/experiments/2026-09-16-gwalert-no-data-page
    ./run.sh
    uv run python emit_instances.py

Read the committed instance back through the snapshot:

    cd ~/GridWorks/experiments/2026-09-16-gwalert-no-data-page
    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/gw.experiment.run-000.json').read_bytes()))"

No `gw.readings` instance lives here; there is no display CSV.
