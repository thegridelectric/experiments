# alerter-to-alertmanager, 2026-09-30

> What this is: does a `gw.alert` the broker alerter raises reach
> Prometheus Alertmanager through the new tap, page a receiver, and
> close when the alerter resolves it, with the alerter and tap restarted
> while the alert is open? PASS on 2026-09-30; see Found.

## Why

The alertmanager design (OPS-547) replaces the hand-written Telegram
dispatcher with Alertmanager and makes the alerter's one `gw.alert` word
the only thing that crosses into it. The tap (`gwalerter tap`) is the
seam: it consumes the word off the alerter's mic exchange, maps it onto
Alertmanager's intake, and re-posts open alerts so Alertmanager's
`resolve_timeout` never closes an alert the alerter still holds open.
This run is the design's handoff bar: a first-pass alerter that has
provably delivered a `gw.alert` into a notifier's intake and had it
page, before anything goes to the alerts box.

## Setup

Laptop, `gw-dev-rabbit` on `localhost:5672` (vhost `d1__1`), the dev
registry (`gnr api` on `localhost:8000`, `gnr rabbit`) serving the
seeded `d1` universe, and Alertmanager 0.34.1 (release binary for
darwin-arm64, not on PATH: `ALERTMANAGER_BIN` / `AMTOOL_BIN` name it)
with `alertmanager.yml` from this folder: grouped by `category` and
`subject`, `group_wait` 5 s, `repeat_interval` 4 h, `resolve_timeout`
1 h, one webhook receiver on loopback (`webhook_receiver.py`, which
prints every notification). No Telegram chat id was set for this run,
so the receiver's log stands in for the group.

Seven processes from `run.sh`: Alertmanager, the receiver, the alerter
(`gwalerter rabbit`, fresh store under the run dir, `NO_DATA_SILENCE_S`
30, `DETECTOR_TICK_S` 2, fleet root narrowed to the mocked spruce), the
tap (`gwalerter tap`, `TAP_RESEND_S` 20, same store), the mock scada from
`../2026-09-15-alerter-no-data/mock_scada.py` (talk 20 s, quiet 60 s,
resume 20 s), then a second alerter and a second tap started on the same
store while the alert is open. Nothing deployed is touched.

## Protocol

1. `amtool alert add` a hand alert; the receiver must print it.
2. Alerter and tap up; the alerter's log shows spruce tracked; the tap
   logs its bind and `Open at boot: 0`.
3. The mock goes quiet. Within 30 s plus a tick the alerter raises
   `Firing` `NoData`, the tap logs the post, `amtool alert query` lists
   it with `alertname=NoData category=House subject=…spruce.ta`, and
   the receiver prints the firing notification.
4. The mock resumes. The alerter sends `Resolved` with the same
   `AlertId`; `amtool` no longer lists it; the receiver prints the
   resolved notification.
5. Between 3 and 4 the alerter and the tap are stopped and restarted on
   the same store: the second tap logs `Open at boot: 1` and re-posts
   it; the receiver prints no second firing (Alertmanager dedups on the
   label set); the second alerter is the one that resolves.

PASS is all five.

## Found

**PASS** (2026-09-30), all five. Code under test: `gridworks-alerter`
`jm/gw-alert` at `bee0564` (the tap commit, made after the run from
the same working tree: `src/gwalerter/tap.py`, `Store.open_alerts`, the
two settings, the `tap` subcommand, on top of `f4d6893`).

- The hand alert reached the receiver 5 s after `amtool alert add`
  (the `group_wait`).
- `Firing` `NoData` raised 00:07:19.880Z, 30.9 s after the last
  talking-phase report (00:06:49Z); the tap posted it within 5 ms;
  Alertmanager listed it with the five labels and three annotations
  (`house="spruce"`, `about` the full alias plus the registry's display
  name, which in the dev seed is the alias itself); the receiver
  printed it at 20:07:24 EDT, again the `group_wait` later.
- The second tap, started 20:07:36 EDT with the alert open, logged
  `Open at boot: 1 alert(s)` and re-posted; the receiver printed
  nothing for it.
- `Resolved` with the same `AlertId` at 00:07:54.649Z, 7 ms after the
  first resume report, sent by the second alerter; the tap posted it
  with `endsAt`; the receiver printed `resolved` at 20:07:54 EDT; the
  post-resume `amtool alert query` lists only the hand alert.
- Alertmanager logged no error. `amtool alert add` warns that an
  unquoted annotation value uses the classic matcher parser; cosmetic,
  and `run.sh` keeps it so the warning is on record.

## Timeline

2026-09-30, EDT.

- 20:06:17 Alertmanager and the receiver up; 20:06:20 hand alert added;
  20:06:25 receiver prints it.
- 20:06:27 alerter 1 up, tracking spruce; 20:06:30 tap 1 bound,
  `Open at boot: 0`.
- 20:06:34–20:06:54 mock talks every 5 s (last report 20:06:49).
- 20:07:19 alerter 1 raises `Firing`; tap 1 posts; 20:07:24 receiver
  prints `firing`.
- 20:07:34 `amtool` lists NoData active; alerter 1 and tap 1 stopped.
- 20:07:36 alerter 2 and tap 2 started on the same store; tap 2
  `Open at boot: 1`.
- 20:07:54 mock resumes; alerter 2 sends `Resolved`; tap 2 posts;
  receiver prints `resolved`.
- 20:08:29 `amtool` lists only the hand alert; everything stopped.

## Analysis notes

- Alertmanager's `endsAt` for a firing alert is zero in the webhook
  payload (`0001-01-01T00:00:00Z`) and `startsAt + resolve_timeout` in
  `amtool`; both mean "open". The tap sets `endsAt` only on `Resolved`.
- The tap's re-post cadence (20 s here, 300 s deployed) is what keeps a
  long-running alert open past `resolve_timeout` (1 h); the open set
  is read from the alerter's store at boot, which is what the restart
  step witnesses.
- Timing is sped up; the rule and the tap read every threshold from
  settings, so the run exercises the deployed code path at another
  scale.
- The alerter's clock is the laptop's; `RaisedMs` / `ResolvedMs` are
  arrival times at the alerter.

## Folder contents & experimental method

All data here is GENERATED by this experiment on the laptop (dev broker,
dev registry, local Alertmanager); nothing from the journal DB or S3; a
re-run produces a new dataset. No deployed service was touched.

- `README.md`: this record.
- `run.sh`: the runbook; starts the seven processes, captures logs to a
  run dir it prints, runs the two `amtool` queries.
- `alertmanager.yml`: the Alertmanager config the run used (the box's
  shape with a webhook receiver); `run.sh` appends a Telegram receiver
  when `TELEGRAM_CHAT_ID` and `TELEGRAM_TOKEN_FILE` are set.
- `webhook_receiver.py`: the loopback receiver that prints what
  Alertmanager delivers.
- `emit_instances.py`: writes `instances/` from the evidence: the two
  `gw.alert` records out of the archived store, and the run record from
  the alerter file log's window.
- `evidence/2026-09-30/provenance.txt`: where each log came from, the
  clocks, the redaction.
- `evidence/2026-09-30/`: the run's logs as captured (`run.log`,
  `receiver.log`, `alertmanager.log`, `alertmanager.yml`,
  `amtool-firing.txt`, `amtool-resolved.txt`, `tap-1.log`, `tap-2.log`,
  `alerter-1.log`, `alerter-2.log`, `alerter-file.log`), broker
  credentials redacted by pattern and nothing else changed;
  `alerter.sqlite`, the alerter's store as the run left it (the two
  alerters wrote it; its `alerts` table holds the one alert's `Firing`
  and `Resolved` payloads).
- `instances/<house>-firing-gw.alert-000.json` and
  `instances/<house>-resolved-gw.alert-000.json`: the alert's two
  transitions, as the alerter recorded them (sema instances; filename
  grammar `<subject>-<condition>-<type.name>-<version>.json`, subject =
  the house alias, condition = the alert's state).
- `instances/gw.experiment.run-000.json`: the run record.

Run (gw-dev-rabbit, the dev registry and the alerter's `.env` in place):

    cd ~/GridWorks/experiments/2026-09-30-alerter-to-alertmanager
    ALERTMANAGER_BIN=/path/to/alertmanager AMTOOL_BIN=/path/to/amtool ./run.sh
    # copy the run dir's logs and store into evidence/<date>/ (redact the
    # broker URL by pattern), then:
    uv run python emit_instances.py evidence/<date>

Read an instance back through the snapshot (no broker needed; prints
the word's fields, evidence included):

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/d1.isone.me.versant.keene.spruce.ta-resolved-gw.alert-000.json').read_bytes()))"

No `gw.readings` instance lives here; there is no display CSV.
