# plant-loop, 2026-11-10

> What this is: the first run of a whole scada fed by a plant over the
> dev broker (OPS-40). The scada on the no-sieg House0 fixture, `ta-plant`
> publishing `sim.plant.flux` to it, ten minutes. Does the scada live,
> and does every channel it takes from the plant change in its reports?
> Verdict: PASS for the 14 channels `SimSensorActor` carries, PASS on
> the re-run for all 35 once every device actor read from the plant, and
> PASS for all 36 on orange, a House0 with a Siegenthaler loop.

## Why

The crossing (`../2026-11-10-plant-crossing/`) showed the plant link
alone hearing the plant. This run puts a scada behind the link:
`SimSensorActor` no longer makes up standing values and posts only what
the link hands it. What a unit test cannot show is the whole path under
its own timers: flux arriving on a paho thread every five seconds beside
the scada's report and snapshot tasks, its watchdog, and the device
actors that still fake their own inputs.

## Setup

Laptop, `d1` universe, `gw-dev-rabbit` (AMQP 5672, MQTT 1885, vhost
`d1__1`) and the local mosquitto. All in `run.sh`:

- **The plant**: `ta-plant` from `gridworks-terminalasset` (`70bb07f`),
  five-second flux, `--seed 20261110`, identity `g.node.gt.json` in this
  folder (`d1.isone.ct.newhaven.hazel1.ta`).
- **The scada**: `gws run --message-summary --seconds-per-report 60` from
  `gridworks-scada`, the working tree on `3426897b` with the
  `SimSensorActor` change uncommitted (seven files; the tree the repo's
  `ci.sh` passed at 12:05 UTC, committed unchanged an hour later as
  `b59bf297` and `7a0488c3`). `SCADA_WEATHER_SOURCE=Sim`, plant link
  `Broker` (the default), no deed, no LTN: the upstream link never
  activates and reports are persisted, not published.
- **One layout file for both**: the fixture pair
  `gw.house0.no.sieg.hazel.*` copied under deployed names into a scratch
  XDG home (`scratch/`, wiped at each start). One edit: the web server's
  port, because another scada on the laptop held the fixture's 8080.
- **Kept apart from that other scada** (an orange1 dev scada and its LTN
  were running throughout): its own XDG config, data and state, and the
  mosquitto's second listener (18831) for its local link. Nothing of
  theirs was stopped or touched.
- **The check**: `loop_check.py` reads the scada's persisted events after
  both have stopped. Each `report.event` is decoded through the scada's
  vendored sema snapshot; the plant-fed channel set comes from the
  scada's own layout loader (channels captured by a `SimSensorActor`
  node).

## Found

**PASS**, all five checks (`logs/loop.json`).

- **The scada outlived the window.** Alive at 600 s; one shutdown event,
  the run's own SIGINT.
- **Ten reports in ten minutes**, one per minute.
- **All 14 plant-fed channels are in the reports and all changed.** 117
  readings each, 51 to 117 distinct values a channel.
- **The values are the plant's walk.** Temperatures stayed within about
  1 °C of the 50 °C start (`hp-lwt` 49.47 to 50.11 °C), flows within
  about 1 gpm of 4.
- **The other 21 channels in the flux found no sensor**, and the link
  said so once each (21 warnings in the scada log). They belong to the
  power meter, the tank modules and the BTU meters, which still read
  their own stand-ins.
- **The plant heard no actuation.** No actor sets a relay through the
  link yet.

## Re-run: every device actor behind the plant

18:27 to 18:37 UTC the same day, same script, same plant and seed. The
logs, `loop.json` and the run instance in this folder are this run's;
the first run's are in this repo's history at `69387ea`.

- **The scada**: the `ow/plant-seam` tree `a75ee9a3` of
  `gridworks-scada`, the one its `ci.sh` passed on, uncommitted on
  `8f086541` because the commits were waiting on a signing passphrase
  (`logs/code-under-test.txt`: `8f086541 44 dirty`). It ran from a
  second checkout of that tree (`SCADA_REPO`), not the working tree. In
  it the power meter, the tank modules and the BTU meter take their
  channels from the plant link, and the relays send their positions.
- **The check** counts every channel whose device senses the plant:
  sim sensor and sim pico words and the simulated power meter. 35 on
  this fixture, which is every channel in the flux.

**PASS**, all five checks.

- **The scada outlived the window**; one shutdown, the run's own SIGINT.
  Ten reports.
- **All 35 plant-fed channels are in the reports and all changed.** The
  29 that are handed on as they arrive hold 114 readings each. The six
  metered channels are read by the meter's own loop and reported on its
  capture rule: 95 to 108 readings for five, and 4 for `hp-odu-pwr`.
- **No flux channel went unread**: the link's "no sensor reads" warning
  did not appear.
- **No pico was called missing and no channel flatlined.** The one
  Warning glitch was `no-ta-deed`, as in the first run.
- **The plant heard 55 actuations across all 11 relays**, `vdc-relay`
  among them.

Not shown by this run: a plant that stops (the outage experiment), and
anything on a board.

## Run on a house with a Siegenthaler loop

2026-11-11, 12:11 to 12:21 UTC: `LOOP_HOUSE=orange ./run.sh`. The scada
on the `gw.house0.orange` fixture, a `gw.house0.layout`, with the same
plant and seed. Its evidence is the scada's persisted events, in
`logs-orange/events-2026-11-11/`, and its record is
`instances/plant.loop-gw.experiment.run-002.json`. The run's
`clock.txt`, `code-under-test.txt`, `plant.log`, `loop.json` and
`g.node.gt.json` are not kept: the window, code and plant counts below
are as those files held them when the run was recorded.

- **The house ran as `d1.isone.ct.newhaven.orange1loop`.** The fixture
  is `orange1`, the house a dev scada and its LTN run as on this
  laptop's broker, so the script renames it in the scratch copy of the
  layout and the operational params. Nothing else in the pair changes.
- **The code**: `gridworks-scada` `a9bf33bf` and
  `gridworks-terminalasset` `74b843f`, both clean. The second is the commit that
  lets the plant read a `gw.house0.layout`.

**PASS**, all five checks.

- **The scada outlived the window**; one shutdown, the run's own SIGINT.
  Ten reports.
- **All 36 plant-fed channels are in the reports and all changed.** The
  30 handed on as they arrive hold 88 readings each in the eight
  reports that decode. The six metered channels hold 76 to 84 for four,
  4 for `hp-odu-pwr` and 2 for `hp-idu-pwr`.
- **No flux channel went unread, no pico was called missing and no
  channel flatlined.** The one Warning glitch was `no-ta-deed`.
- **The sieg loop ran**: Initializing to Blind at boot, to HpOff at
  30 s, back to Blind at 120 s, with the valve travelling toward send,
  then keep, then to FullySend at 204 s. Local control left
  Initializing for HpOffStoreOff at 65 s.
- **The plant heard 63 actuations across all 13 relays**, the two
  `hp-loop-*` relays among them.

**Found: two of the ten reports are not valid `report.event`.** Each
carries an `fsm.atomic.report` from `sieg-loop` with `ReportType`
`Event`, a `FromState` and a `ToState`, and neither `EventEnum` nor
`Event`: a valve move the loop made itself. The word's Axiom 2 wants
all four or none, so the scada's own sema snapshot refuses the whole
report: the 12:13 and 12:16 reports in `logs-orange/events-2026-11-11/`.
The scada on
`main` writes the same two entries on this fixture with no plant at
all, so the plant link is not the cause. The check counts such a report
as a report and reads nothing out of it.

## Timeline

UTC. The first run:

- 12:07:13 plant starting; consuming at 12:07:14.
- 12:07:14 scada starting.
- 12:17:14 scada alive at the end of the window; stopped at 12:17:15.
- 12:17:15 plant stopped.
- 12:17:16 check ended, exit 0.

The re-run, from `logs/clock.txt`:

- 18:27:28 plant starting and consuming; scada starting.
- 18:37:28 scada alive at the end of the window; stopped at 18:37:30.
- 18:37:30 plant stopped.
- 18:37:31 check ended, exit 0.

The orange run, as its `clock.txt` held it:

- 12:11:37 plant starting; consuming at 12:11:38; scada starting.
- 12:21:38 scada alive at the end of the window; stopped at 12:21:40.
- 12:22:15 plant stopped.
- 12:22:16 check ended, exit 0.

## Analysis notes

- The scada's tree was not a commit when it ran: the commit of the
  change under test was waiting on a signing passphrase, so
  `logs/code-under-test.txt` says `3426897b 7 dirty`. The seven files
  were last written between 11:43 and 11:59 UTC, before the run, and
  went in as they stood as `b59bf297` and `7a0488c3`.
- "No watchdog death" is read from the process staying up and from the
  absence of any shutdown event but the run's own. The sim sensors'
  keepalive is a timer of their own, so a silent plant would not trip
  the watchdog either; that is the outage experiment, not this one.
- Reports were read from the scada's event store, not off the wire. With
  no LTN the upstream link stays down and nothing is published.
- A 100 s trial of the same script ran first (11:47 UTC, one report, same
  verdict) to shape the check; its logs were replaced by this run.
- The reports hold 117 readings a channel against some 120 fluxes sent:
  nothing thinned them on the way in.
- A `capture_broker.py` belonging to another experiment was running on
  the same broker; this run's flux is in that capture.

- The orange run was started detached from its shell, which left
  SIGINT ignored in the plant, so the plant ran on for 35 s after the
  scada stopped and was ended with SIGTERM. The verdict is read from
  the scada's events and does not turn on how the plant stopped.
- `logs/loop.json` is the hazel re-run's verdict as the check wrote it
  then, before `undecodable_reports` was a field.

## Folder contents & experimental method

All data here was GENERATED by this run on the laptop; none of it is in
the journal DB or the eventstore, and a re-run produces a new dataset.
The run started and stopped two laptop processes of its own (the plant
and a scada in a scratch home) and touched nothing deployed and no other
running service.

- `README.md`.
- `run.sh`: the whole run, wall clock per step. Needs `gw-dev-rabbit`,
  the local mosquitto (18831) and the sibling `gridworks-scada` and
  `gridworks-terminalasset` checkouts; `SCADA_REPO` names another scada
  checkout.
- `loop_check.py`: the verdict from the scada's persisted events.
- `emit_instances.py`: the hazel run's record from its logs.
- `g.node.gt.json`: the plant's dev identity, as the plant wrote it.
- `logs/clock.txt`, `logs/code-under-test.txt`, `logs/plant.log`,
  `logs/loop.json` (the verdict, with what the reports hold for each
  plant-fed channel), `logs/loop_check.stderr` (empty).
- `instances/plant.loop-gw.experiment.run-001.json`.
- `logs-orange/events-2026-11-11/`: the orange run's scada events, as
  the scada persisted them. `loop_check.py` reads them from
  `<scratch>/data/gridworks/scada/event/<day>/`.
- `instances/plant.loop-gw.experiment.run-002.json`, emitted when the
  orange run was recorded.
- `logs/scada.log` (1 MB), `scratch/` and
  `scratch-orange/` (each scada's XDG home, with its event store) stay
  on this laptop, gitignored.

Regenerate everything from scratch:

    ./2026-11-10-plant-loop/run.sh
    uv run python 2026-11-10-plant-loop/emit_instances.py

`LOOP_HOUSE=orange ./2026-11-10-plant-loop/run.sh` runs orange again,
a new run with logs of its own in `logs-orange/`.

No readings instance is kept, so there is no display CSV.
