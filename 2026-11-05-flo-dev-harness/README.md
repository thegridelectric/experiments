# flo-dev-harness, 2026-11-05 to 2026-11-10

> What this is: the first FLO round trip on a laptop (OPS-514). A sim
> scada and its LTN from `gridworks-scada` and the FLO service from
> `gridworks-flo` ran on the dev broker, and the LTN bid off the FLO's
> answer. Rung 1 passed on 2026-11-05. The logbook line is the index
> record, and the stand-up steps are `../dev-stack-recipe.md` "A FLO
> round trip".

## Why

The FLO runs in production as `hw1.flo`, and oak's LTN asks it over the
broker. Without a house, though, nobody could watch a round trip end to
end, change one side and watch again. The harness is that loop on a
laptop: the broker, the scada's MQTT link, the gwbase actor and the
optimizer are all real, and only the plant is simulated.

## Setup

The laptop's dev broker (`gw-dev-rabbit`, vhost `d1__1`), the registry
seeded with the `d1` universe, `gridworks-flo` `main` as `d1.flo` with
bruce from the sibling `optimal-flexibility`, and `gridworks-scada`
`jm/flo-over-the-broker` (PR 605) for the sim scada and the LTN, on the
orange pair (the simulated House0: one 120 gallon tank, AllTanks, bruce
tuning; LTN `d1.isone.ct.newhaven.orange1`). The broker firehose capture
ran throughout. Nothing deployed was touched.

The bar for rung 1: the LTN's bid for a slot is built from the FLO's
answer, inside the LTN's timeout.

## Found

- **Rung 1: PASS.** With `LTN_BID_LEAD_S=600`, the LTN asked at
  13:50:56 ET for the 14:00 slot, the FLO answered at 13:50:59, and the
  bid was on the broker at 13:50:59.922. The capture has
  `…orange1.to.flo.flo-params` and `d1-flo.to.ltn.flo-recommendation` on
  `amq.topic`, and the LTN's copies of both to the scada.
- Six milliseconds after the bid, the scada shut down on the LTN's copy
  of the recommendation (`Scada does not expect to receive
  FloRecommendation`). The running scada predated the handler merged to
  `main` on 2026-11-04 (`085fbad5`, #604). The branch took it in a merge
  at 13:54, and the 13:55 restart runs it.
- A restarted LTN waits for the scada's operating status, because the
  scada sends it at boot and then only when a field changes. The waits
  were 43 s and 115 s (OPS-669).
- The sim scada's buffer goes stale for about 50 s every four minutes,
  which flaps `ScadaBlind` (OPS-670).
- `gridworks-ltn`'s `ci.sh` publishes on the same vhost. On 2026-11-09
  its stand-in `latest.price` made the harness LTN drop its bid
  (OPS-671).

The harness then served OPS-665 on 2026-11-09 and 2026-11-10: the
`flo.recommendation` 001 words journaled from orange1's slots, and the
web-backend route and visualizer page that read them.

Rung 2, stepped time (the scada and LTN on `Timestep` with the time
coordinator broadcasting one simulated hour per wall minute), did not
run.

## Timeline

ET, from `logs/clock.attempt1.txt` and `logs/clock.txt`.

- 2026-11-05 12:08 to 12:28: first attempt, with a layout whose tuning is
  alice. Torn down before the hour, because alice needs an operator hold
  under which the scada refuses dispatch.
- 12:31: broker restarted clean. 13:12: the orange pair placed. 13:21:
  the FLO started.
- 13:35 to 13:47: the scada stopped by hand twice and the LTN restarted
  three times, which showed the operating-status wait.
- 13:50:56: request. 13:50:59: answer. 13:50:59.922: bid.
- 13:54: the scada branch merged `main`. 13:55: scada restarted.
- 2026-11-09 13:16 to 14:10: OPS-665 runs. The FLO answered at 13:45:52
  with two pairs, and a seam-test `latest.price` dropped the bid at
  13:49:38.
- 2026-11-10 07:11 to 08:55: OPS-665 runs. The FLO answered at 07:13:14
  with two pairs, and the visualizer page was checked against the
  journaled 001 word.

## Folder contents & experimental method

All data here was GENERATED on the laptop's dev broker. None of it is in
the journal DB or the eventstore, and a re-run is a new dataset. Nothing
deployed was touched.

- `README.md`: this record.
- `logs/clock.attempt1.txt`, `logs/clock.txt`: each step's wall clock, ET,
  as the sessions wrote them.
- `emit_instances.py`: writes the `gw.experiment.run` for rung 1 through
  the vendored snapshot.
- `instances/d1.isone.ct.newhaven.orange1-flo.round.trip-gw.experiment.run-001.json`:
  the rung 1 run, PASS.
- `captures/` and `logs/*.log` (gitignored): the firehose captures and
  each service's stdout, kept on the laptop that ran them.

Regenerate the instance:

    uv run python emit_instances.py

There is no reading data, so there is no display CSV.
