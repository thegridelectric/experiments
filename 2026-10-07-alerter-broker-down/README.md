# alerter-broker-down, 2026-10-07

> What this is: when the broker goes away, does the prober page
> `BrokerUnreachable` through the tap with no broker involved, does the
> alerter hold its `NoData` pages while the broker is down, and do both
> doors resolve when the broker returns with no `NoData` afterwards?
> FAIL on 2026-10-07: the prober passed, the tap paged four minutes
> late, and a `NoData` fired on reconnect; see Found.

## Why

The alerter is a consumer of the one broker the houses use, so a broker
outage is silent to it: it hears nothing and sees every house as silent
at once. Without the prober that outage surfaces as one `NoData` page per
house, ten minutes in, naming the wrong cause. The broker-alerter design
(OPS-545) answers with a prober that checks the broker's two doors from
outside the broker path and raises one `BrokerUnreachable` per door into
the alerter's store, which the tap pages from on its reconcile pass; the
`NoData` rule holds while one is open and re-floors when it resolves.
The tests pin each piece in isolation; this run is the witness against
a real broker stop, the bar before the prober runs on the alerts box.

## Setup

Laptop, `gw-dev-rabbit` (docker) on `localhost:5672` AMQP and
`localhost:1885` MQTT (TLS off), the dev registry (`gnr api` on
`localhost:8000`, `gnr rabbit`) serving the seeded `d1` universe, and an
Opsgenie Alert API integration key plus the id of the one team,
GridWorks Dev (`OPSGENIE_API_KEY`, `OPSGENIE_TEAM_ID` in the experiments
`.env`, gitignored, or the environment of `run.sh`; nothing in this
folder holds either). The run pages whoever
is on call on the Millinocket schedule.

Four processes from `run.sh`, each under a restart loop standing in for
systemd's `Restart=always`: the alerter (`gwalerter rabbit`, fresh store
under the run dir, `NO_DATA_SILENCE_S` 120, `DETECTOR_TICK_S` 2, fleet
root narrowed to the mocked spruce), the tap (`gwalerter tap`,
`TAP_RECONCILE_S` 20, same store), the prober (`gwalerter probe`,
`PROBE_INTERVAL_S` 10, `PROBE_FAILURES_TO_RAISE` 3, the AMQP door the
alerter's own URL, the MQTT door `localhost:1885` plain), and the mock
scada from `../2026-09-15-alerter-no-data/mock_scada.py` talking every
5 s throughout. The broker container is stopped for 240 s, twice the
`NoData` threshold, and started again. Nothing deployed is touched.

## Protocol

1. All four up; 60 s of normal traffic: the prober logs both doors
   answering, the alerter tracks spruce, no alert.
2. `docker stop gw-dev-rabbit`. Within about 40 s the prober raises
   `Firing` `BrokerUnreachable` on each door (`localhost:5672`,
   `localhost:1885`); within a further 20 s the tap's reconcile pass
   creates both in Opsgenie (the tap's consumer has died with the broker
   and its restart loop brings it back; the reconcile runs at each
   boot). Through the 240 s the alerter raises no `NoData`, though
   spruce has been silent past 120 s.
3. `docker start gw-dev-rabbit`. The prober's first success on each door
   resolves its alert; the tap closes both in Opsgenie. The mock
   reconnects and talks.
4. 150 s on, past the `NoData` threshold counted from the broker's
   return: no `NoData` has been raised.

PASS is all four. A `NoData` at any point is FAIL.

## Found

**FAIL** (2026-10-07), steps 1 and 3 met, steps 2 and 4 not. Code under
test: `gridworks-alerter` `jm/gw-alert` working tree (the prober,
uncommitted at run time).

- The prober did its part. Both doors answered through step 1. 29 s
  after the stop (09:48:31) it raised `BrokerUnreachable` on
  `localhost:5672` and on `localhost:1885`, one alert each, into the
  store; 6 s after the start (09:52:11) it resolved both. The four
  `gw.alert` records are in `instances/`.
- **The tap did not page while the broker was down.** `Tap.run` opens
  the broker connection before its first reconcile, so with the broker
  down it died at connect and its restart loop brought it back every
  3 s to die again; the step 2 listing (09:49:33) holds only this
  morning's three closed alerts. At 09:52:08, its first connect after
  the broker returned, the boot reconcile created both alerts in
  Opsgenie (tiny ids 1251, 1252) and the 09:52:30 pass closed them,
  the prober having resolved them 19 s earlier. Opsgenie saw a
  four-minute outage as two alerts open for 20 s, four minutes late.
- **`NoData` fired.** At 09:52:16, 5 s after the broker was back, the
  alerter raised `NoData` on spruce with "since 2026-10-07 13:47:57Z",
  the mock's last report before the stop (tiny id 1253); the mock's
  first report resolved it 48 ms later. Cause: `AlerterActor.run_detectors`
  skips evaluation while the actor is not consuming, which was the
  whole outage, so the rule never saw the open `BrokerUnreachable`
  alerts and never re-floored. Its first tick after reconnecting found
  the alerts already resolved and the house silent for 258 s.
- The alerter process never restarted: its gwbase actor reconnected by
  itself at 09:52:15. The tap restarted 80 times and the mock 78.

## Timeline

2026-10-07, EDT.

- 09:46:55 alerter up, tracking spruce; 09:47:00 prober up, both doors
  answering; tap bound; mock talking.
- 09:48:02 `docker stop gw-dev-rabbit`; tap and mock die, restart loops
  begin; the alerter's consumer drops.
- 09:48:31 prober raises `BrokerUnreachable` on both doors (3 failures
  10 s apart).
- 09:49:33 Opsgenie listing: nothing new.
- 09:52:05 `docker start gw-dev-rabbit`.
- 09:52:08 tap connects, boot reconcile creates both alerts in Opsgenie.
- 09:52:11 prober resolves both.
- 09:52:15 alerter rebinds its queue; 09:52:16 raises `NoData`, tap
  creates it; mock's first report resolves it 48 ms later, tap closes it.
- 09:52:30 tap reconcile closes both `BrokerUnreachable` alerts.
- 09:53:20 and 09:55:50 listings: six closed alerts, three of them this
  run's; everything stopped.

## Analysis notes

- Step 4 is moot as run: the `NoData` fired at reconnect, not after the
  threshold, and nothing fired in the 150 s after; the hold's claim is
  still untested until the detector loop runs during an outage.
- The tap's restart loop is systemd's `Restart=always` at 3 s; on the
  box the same crash loop would run at `RestartSec=5`.

- The run's Opsgenie listing by `source` also shows alerts earlier runs
  left closed (the 2026-10-07 alerter-to-opsgenie run's three); the
  typed view is filtered by eye to this run's window.
- The dev broker's MQTT door is plain (`1885`, TLS off) where the
  fleet's is TLS (`8883`); `PROBE_MQTT_TLS=false` selects the plain
  connect. Everything else is the deployed code path at another scale.

## Folder contents & experimental method

All data here is GENERATED by this experiment on the laptop (dev
broker, dev registry) against the Opsgenie account the fleet pages
through; nothing from the journal DB or S3; a re-run produces a new
dataset and pages the team again. The run stops and starts the laptop's
dev broker container; no deployed service is touched.

- `README.md`: this record.
- `run.sh`: the runbook; starts the four processes under restart loops,
  stops and starts the broker container, captures logs to a run dir it
  prints, and saves Opsgenie's raw listing three times (down, back,
  final) with the typed view beside each.
- `emit_instances.py`: writes `instances/` from the evidence: every
  `gw.alert` record in the archived store (the prober's two doors'
  Firing and Resolved; any `NoData`, of which the bar is none), the
  `gw.opsgenie.alert` words out of the final listing, and the run
  record. Takes the evidence folder and the verdict (`Pass`, `Fail`,
  `Inconclusive`).
- `evidence/<date>/`: the run's logs as captured (`alerter.log`,
  `tap.log`, `prober.log`, `mock.log`, `run-stdout.log`, the alerter's
  file log `d1.alerts.log`), broker credentials redacted by pattern and
  nothing else changed; `opsgenie-{down,back,final}.json` the listings
  as Opsgenie returned them and `.txt` their typed views;
  `alerter.sqlite` the store as the run left it; `provenance.txt`.
- `instances/`: see `emit_instances.py`.

Run (gw-dev-rabbit, the dev registry and the alerter's `.env` in place):

    cd ~/GridWorks/experiments/2026-10-07-alerter-broker-down
    ./run.sh 2>&1 | tee run-stdout.log   # credentials from ../.env
    # copy the run dir's logs and store into evidence/<date>/ (redact the
    # broker URL by pattern), then:
    uv run python emit_instances.py evidence/<date> Pass

Read an instance back through the snapshot (no broker needed):

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/gw.experiment.run-001.json').read_bytes()))"

No `gw.readings` instance lives here; there is no display CSV.
