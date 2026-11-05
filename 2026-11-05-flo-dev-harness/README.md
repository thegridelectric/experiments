# flo-dev-harness, 2026-11-05

> What this is: the local dev harness for flo-as-a-service (OPS-514): a
> sim scada, its LTN from `gridworks-scada` and the FLO service from
> `gridworks-flo` on one laptop's dev broker, the LTN asking the FLO for a
> slot and bidding off the answer. Found is open; the setup steps below
> are the record so far and are written so anyone on the team can stand
> the harness up on their own laptop.

## Why

The FLO runs in production as `hw1.flo` and oak's LTN asks it over the
broker, but nobody can watch a round trip end to end, change one side
and watch again, without a house. The harness is that loop on a laptop:
every piece real (the broker, the scada's MQTT link, the gwbase actor,
the optimizer), only the plant simulated and the clock, later, stepped.

## Setup

Repos as siblings under one directory, on these branches:

| repo | branch | role |
|---|---|---|
| gridworks-base | main | the dev broker |
| grid-node-registry | main | `d1.flo` in the dev universe |
| gridworks-flo | main | the FLO service |
| gridworks-scada | `jm/flo-over-the-broker` (PR 605) | the sim scada and the LTN |
| optimal-flexibility | main (sibling checkout, `thdfw`) | bruce |
| experiments | this folder | the capture and the record |

Docker and uv installed. The scada venv built with `tools/mkenv.sh` from
the scada repo root.

## Protocol

Each step says what to run and what "ready" looks like. Times are ET.

1. **Broker.** `cd gridworks-base && ./arm.sh` (`./x86.sh` on Intel).
   Ready: `docker ps` shows `gw-dev-rabbit`; the management UI is on
   15672, vhost `d1__1`, MQTT door 1885.
2. **Registry database.** `cd grid-node-registry && docker compose up -d`
   (container `gnr-postgres`, host port 5435). `.env` from `template.env`;
   it MUST have `GNR_API_PORT=8010`, because 8000 is the sim scada's.
   `uv sync --all-groups`.
3. **Seed the dev universe.** `uv run gnr seed-dev` (`--wipe` if the
   registry was seeded before; the GNodeIds derive from the alias, so a
   re-seed keeps every id). Ready: `✓ seeded 29 d1 GNodes`.
4. **Read façade.** `uv run gnr api` in its own window. Ready:
   `curl localhost:8010/docs` is 200 and
   `curl localhost:8010/gnr/g-node-by-alias/d1.flo` serves class `Flo`.
5. **The FLO's identity.** `mkdir -p ~/.config/gridworks/flo &&
   curl -s localhost:8010/gnr/g-node-by-alias/d1.flo | python3 -m json.tool
   > ~/.config/gridworks/flo/g.node.gt.json`. The served record is the
   identity file, as on the production box.
6. **The layout pair.** `cd experiments && ./put_layout.sh dev check`;
   if any file differs, `./put_layout.sh dev <change>` places the scada
   repo's orange fixtures (the simulated House0 pair, one 120 gallon
   tank, AllTanks, bruce tuning) under the deployed names in
   `~/.config/gridworks/scada/` and `~/.config/gridworks/ltn/`. The
   script's house argument also takes willow or nolan; nolan is not for
   this harness, since its FLO tuning is alice. The orange LTN is
   `d1.isone.ct.newhaven.orange1`, in the `d1` universe, so its FLO is
   `d1.flo` with no configuration.
7. **The FLO service.** `cd gridworks-flo && cp template.env .env`
   (the defaults are the dev broker and `d1.flo`);
   `uv sync --all-groups --all-extras` (the bruce extra installs the
   sibling `../optimal-flexibility` editable); `uv run gwflo rabbit`.
   Ready: the log says `Queue d1.flo-… bound with rj.*.*.*.*.d1-flo` and
   `Binding d1.flo-… to amq.topic with gw.*.to.flo.flo-params`.
8. **bruce's matrix for the plant shape.** bruce walks a graph of store
   states and heat-pump actions, and the next state of every (state,
   action) pair is computed once per plant shape and cached as
   `~/.config/bruce/graph_optimizer/heat_pump_water_tank_<hash>.matrix.npz`;
   the hash is over the shape fields only (layers, gallons, lift, the RWT
   buckets, the thermal caps, the longest step, the discharge threshold),
   so no per-request number changes it. bruce refuses a request whose
   shape has no file. The orange pair is one 120 gallon tank at 9 layers
   with the fleet tuning: hash `268a5f12`, which is also bruce's default
   geometry. Three ways to get it, in order of preference:
   - copy the file (175 KB, deterministic) from a laptop or the flo box
     into `~/.config/bruce/graph_optimizer/`;
   - build it once with bruce's own test: in `optimal-flexibility`,
     `cp .env.example .env` (it sets `CAN_COMPUTE_TRANSITION_MATRICES=true`,
     which bruce reads from that file) and `uv run pytest
     tests/test_generate_bid.py`, about fifteen minutes;
   - leave that `.env` in place and let the service build it on the
     first request, which costs that slot (the LTN times out and bids its
     fallback) and answers from the cache the next hour.

   Ready: `ls ~/.config/bruce/graph_optimizer/` shows the `268a5f12`
   file, and `optimal-flexibility/.env` is absent or not `true`, so the
   service never builds in the request path.
9. **The scada and LTN env.** `gridworks-scada/gw_spaceheat/.env`:

       SCADA_GRIDWORKS_MQTT__PORT=1885
       LTN_SCADA_MQTT__PORT=1885
       LTN_SCADA_MQTT__TLS__USE_TLS=false
       LTN_DASHBOARD__PRINT_GUI=false
       LTN_WEATHER_SOURCE=Sim
       LTN_BID_LEAD_S=120

   The scada's MQTT settings default to TLS off; the LTN's default to
   TLS on, so the LTN needs both lines. The bid lead puts the request
   two minutes before the hour instead of three.
10. **Capture.** `cd experiments && uv run python capture_broker.py
    2026-11-05-flo-dev-harness/captures > 2026-11-05-flo-dev-harness/logs/capture.log`.
    Ready: `capturing vhost d1__1`. Start it before the LTN and scada.
11. **The LTN.** From `gridworks-scada/gw_spaceheat`:
    `venv/bin/python -c "import sys; from ltn_app import LtnApp; sys.exit(LtnApp.main(env_file='.env', return_int=True))"`,
    the box service's command. Ready: `scada_mqtt: … --> awaiting_peer`,
    then `Main loop idle: waiting for gw.house.operating.status` until the
    scada is up.
12. **The sim scada.** From the scada repo root:
    `gw_spaceheat/venv/bin/gws run --message-summary`. Ready: the LTN's
    link goes active and the LTN logs the operating status.
13. **The round trip.** At `LTN_BID_LEAD_S` before the hour the LTN logs
    the request; the FLO logs `Request from d1.isone.ct.newhaven.orange1
    for slot <start>: flo.tuning.bruce` and `Answered … in <n> s: <k> pairs
    from bruce`; the LTN logs the bid for the slot. The capture has both
    wrapped words on `amq.topic`.

The pass criterion for rung 1 is the LTN's bid for the slot built from
the FLO's answer, within the LTN's timeout. Rung 2 steps the clock: the
scada and LTN on `Timestep` with the time coordinator broadcasting one
simulated hour per wall minute, several slots in a session.

## Found

Open. A first attempt on 2026-11-05, 12:08 to 12:28 ET, ran steps 1 to
12 with the Nolan fixtures and was torn down before the hour: Nolan's
tuning is alice, and `flo.tuning.alice` requires an operator hold (ops
word axiom 6) under which the scada refuses dispatch, so that LTN never
asks the FLO. Three things it taught are in the steps: the registry's
older `.env` had no `GNR_API_PORT` and the façade took 8000; the sim
scada starts from the scada repo root; and the orange shape's matrix is
bruce's default geometry, already cached on a laptop that built oak's.
The second attempt, with orange, is a step-by-step walk from a clean
broker; its times are in `logs/clock.txt`.

## Folder contents & experimental method

All data here is GENERATED on the laptop's dev broker; none of it is in
the journal or the eventstore and a re-run is a new dataset. Nothing
deployed is touched.

- `README.md`: this record.
- `captures/` (gitignored `*.jsonl`): the broker firehose capture.
- `logs/`: `clock.txt` (each step's wall clock), `capture.log`, and the
  LTN and scada stdout (`*.log`, gitignored).
- `instances/`: the `gw.experiment.run` record, once Found closes.
