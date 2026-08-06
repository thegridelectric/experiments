# 2026-06-11 — Sim-time first bridge run (crossing → scada + LTN stand-in)

**Why:** the open sim-time question "first live bridge run" — does the real
time coordinator's `sim.timestep` actually reach MQTT subscribers through
the gwbase crossing, and do scada-side listeners receive it?

**Found (VERIFIED, scoped):** the crossing works. `tc-hello` (`d1.tc`)
broadcasting `sim.timestep` over AMQP → gwbase topology binding
(TimeCoordinator publish exchange → `amq.topic`, key `rjb.#`) → MQTT topic
`rjb/d1-tc/time/sim-timestep`. A real scada-side `SimTimeListener` received
every step, monotonically; an independent observer recorded all traffic.
11 broadcasts crossed; scada listener got 9, a second stand-in listener 10
(edge-of-window connect timing).

**Not verified (fidelity gaps → next iterations):** the real LTN running
its own sim-time path (used a stand-in `SimTimeListener`); the real
scada↔LTN links driven off coordinator time with the real keepalive (used
harness ping/acks). North stars for "really shines": the LTN's ASCII
dashboard showing live temperatures + relay/heat-pump + power under sim
time, and/or a CSV of an hour of simulated scada telemetry produced under
sped-up coordinator time.

**Reproducer:** `harness.py` + observer — NOT yet in this repo (still
in a local workspace while being raised to dashboard/CSV fidelity, to
avoid committing a stand-in; its folder here is owed). **Raw bundle:** `sim-time-experiment-20260611-1825.zip`
(provenance, out of git). **Broker:** `gw-dev-rabbit` MQTT `:1885`.
