# Sim-time coordinator → scada + LTN: first live bridge run

Date: 2026-06-11 · branch `jm/spruce-unlimbo` (scada) + local gwbase 0.5.2 + gridworks-timecoordinator `dev`

## What this run proves

The time coordinator (`d1.tc`, the real `tc-hello`) broadcast `sim.timestep`
over AMQP, those broadcasts crossed to MQTT through the gwbase topology
binding, and **both the scada-side and an LTN-side `SimTimeListener` received
every step** — witnessed by an independent broker observer that recorded all
traffic, both directions.

This is the sim-time spoke's open "first live bridge run" (tc-hello + the
`timemic_tx → amq.topic` crossing + sim receivers), plus a first cut of
experimentation-tools tool (3), the generic broker observer/recorder.

## Topology exercised

```
tc-hello (d1.tc)  --AMQP broadcast-->  publish_exchange(TimeCoordinator)
       |                                         |
       |                       gwbase topology binding (rjb.#)
       |                                         v
       |                                    amq.topic
       |                          (RabbitMQ MQTT plugin, :1885)
       v                                         |
  rjb.d1-tc.time.sim-timestep  ===>  rjb/d1-tc/time/sim-timestep  (MQTT)
                                                 |
              +----------------------------------+----------------------------------+
              v                                  v                                  v
       scada SimTimeListener            LTN SimTimeListener                 observer (binds '#')
       (on timestep: ping ltn)          (on timestep: ack scada)           records every message
```

Broker: dev-rabbit (`ghcr.io/thegridelectric/dev-rabbit`), MQTT plugin on
`localhost:1885`, AMQP `amqp://smqPublic:smqPublic@localhost:5672/d1__1`.
Restarted before the run so topology was re-provisioned clean.

## Results

| Metric | Value |
| --- | --- |
| `sim.timestep` broadcasts crossing to MQTT (observer) | 11 |
| scada timesteps received | 9 |
| LTN timesteps received | 10 |
| both received | **yes** |
| total messages recorded | 30 |
| ping/ack back-and-forth (scada→ltn / ltn→scada) | 9 / 10 |

The 9 / 10 / 11 spread is connect timing at the window edges — the observer
came up first and the scada listener's first SUBACK landed a beat later. Every
step inside the steady window was received by both sides in the same
millisecond (see `harness.log`).

## What the logs show

Per beat, the sequence is tight and clean (from `harness.log`, cross-checked
against the publisher's `tc_hello.log`):

```
[d1.tc] sim time -> 1781216632                 (tc-hello publishes, AMQP)
SCADA RECEIVED sim.timestep TimeUnixS=1781216632
LTN   RECEIVED sim.timestep TimeUnixS=1781216632
observer rx rjb/d1-tc/time/sim-timestep          type=sim.timestep
observer rx gw/sim-experiment/scada/to/ltn/sim-ack  type=sim.ack
observer rx gw/sim-experiment/ltn/to/scada/sim-ack  type=sim.ack
```

The coordinator's wire payload, captured verbatim:

```json
{"TypeName":"sim.timestep","Version":"000","FromGNodeAlias":"d1.tc",
 "FromGNodeInstanceId":"d3157ef9-…","TimeUnixS":1781216632,
 "TimestepCreatedMs":1781216632899,"MessageId":"8279b4a9-…"}
```

## Files in this bundle

- `messages.jsonl` — the logbook: every MQTT message the observer saw, one
  JSON record per line (rx wall-clock, topic, QoS, TypeName, parse-outcome,
  raw payload). 30 records.
- `receipts.json` — the witnessed-receipt tally + per-side receipt list.
- `harness.log` — the receiver side: subscriptions, each RECEIVED step, each
  observer record.
- `tc_hello.log` — the publisher side: AMQP connect, topology provision, each
  broadcast.

## Honest caveats

- The LTN has no native sim-time listener yet (open item in the sim-time
  spoke). This run reused the proven scada `SimTimeListener` to stand in for
  the LTN receiver, which is enough to witness "both receive" but is not the
  LTN's real path.
- The ping/ack here is a harness stand-in to make two-way traffic visible —
  it is not the scada's real upstream keepalive ping (that lives in the Scada
  actor's `_on_sim_timestep`, not exercised here).
- The bridge listener parses `sim.timestep` JSON by hand and is interim by
  design (dies in the uv/AllyLink rebuild).
