"""Basic SimulatedPlant + async-capture flux trigger (scratch EDD step).

The smallest piece of the gwta plant: hold one tank-depth temperature, advance it
on a clock with a (deliberately strange) inner model, and emit a `sim.plant.flux`
ONLY when the value moves by >= the channel's async-capture delta since the last
emit -- the `AsyncCaptureDelta` semantics the real `ChannelConfig` carries. Then
verify that the flux triggers on async change, not every tick.

No `sema/` edits and no broker: in-process and self-verifying. `emit_cb` is the
seam where a real rabbit publish (`sim.plant.flux` on the plant broker) lands
later -- and where the value would round-trip through the real `SimPlantFlux`
type once it is hand-added to gwsproto.

Run: python3 simulated_plant.py
"""

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

OUT = Path(__file__).parent / "sim_plant_out"

# --- the one channel we simulate: a store-tank depth temperature ---
CHANNEL = "tank1-depth1"
TELEMETRY = "WaterTempCTimes1000"  # scaled int: milli-degrees C

# TODO(wire-in): this async-capture limit is HARD-CODED here. When the plant is
# wired into a layout, bind it to the Component's ConfigList entry for this
# channel -- `ChannelConfig.AsyncCaptureDelta` (PositiveInt, in the channel's
# units), the canonical async threshold the scada uses
# (gwsproto type_helpers/channel_config_base.py:14; sema channel.config/000:
# "published value is >= AsyncCaptureDelta"). Same units as the value below.
ASYNC_CAPTURE_DELTA = 500  # 0.5 C (in milli-deg C)


def strange_inner_model(t: float) -> int:
    """A deliberately strange inner model for one tank temperature (milli-deg C).

    Hot water around 48 C, wandering: a slow sine (the big swing), a faster ripple
    (intentionally smaller than the async delta, so ripple alone does NOT trigger),
    and a gentle upward drift. Quirky on purpose -- we only need it to cross the
    delta at uneven intervals so the async trigger is genuinely exercised.
    """
    base = 48_000
    slow = 4_000 * math.sin(t / 30.0)  # +/-4 C slow swing
    ripple = 300 * math.sin(t / 3.0)   # +/-0.3 C ripple (below the 0.5 C delta)
    drift = 20 * t                     # slow warm-up
    return int(base + slow + ripple + drift)


def _iso_ms() -> str:
    """Human-readable ISO-8601 with millisecond precision and Z -- matches the
    `utc.iso8601.millis` format `sim.plant.flux.ActualTimeUtc` uses."""
    now = dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


@dataclass
class SimulatedPlant:
    """Holds physical state, advances on a clock, and emits `sim.plant.flux` when a
    channel crosses its async-capture delta since the last emit."""

    async_delta: int = ASYNC_CAPTURE_DELTA
    last_emitted: dict = field(default_factory=dict)  # channel -> last emitted value
    emit_cb=None  # function(flux: dict) -- the broker-publish seam

    def step(self, t: float, sim_unix_ms: int) -> None:
        value = strange_inner_model(t)
        prev = self.last_emitted.get(CHANNEL)
        if prev is None or abs(value - prev) >= self.async_delta:
            self.last_emitted[CHANNEL] = value
            self._emit(CHANNEL, value, sim_unix_ms)

    def _emit(self, channel: str, value: int, sim_unix_ms: int) -> None:
        flux = {
            "ChannelNameList": [channel],
            "ValueList": [value],
            "ScadaReadTimeUnixMs": sim_unix_ms,  # sim time
            "ActualTimeUtc": _iso_ms(),          # wall-clock, human-readable
            "TypeName": "sim.plant.flux",
            "Version": "000",
        }
        if self.emit_cb is not None:
            self.emit_cb(flux)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    emitted: list[dict] = []
    plant = SimulatedPlant()
    plant.emit_cb = emitted.append

    ticks = 200
    t0_ms = 1_700_000_000_000  # arbitrary sim epoch (sim time, not wall clock)
    per_tick_values = []
    for i in range(ticks):
        t = float(i)
        per_tick_values.append(strange_inner_model(t))
        plant.step(t, t0_ms + i * 1000)

    vals = [e["ValueList"][0] for e in emitted]

    # 1. every consecutive emit moved >= delta from the previous emit
    gaps_ok = all(abs(vals[k] - vals[k - 1]) >= plant.async_delta for k in range(1, len(vals)))
    # 2. async-gated: far fewer emits than ticks (NOT every tick)
    gated = 0 < len(emitted) < ticks
    # 3. no missed crossing: a reference async filter over every tick's value
    #    yields exactly the same emit sequence
    ref, last = [], None
    for v in per_tick_values:
        if last is None or abs(v - last) >= plant.async_delta:
            ref.append(v); last = v
    matches_reference = vals == ref
    # 4. flux shape carries the sim.plant.flux fields (incl. both timestamps)
    need = {"ChannelNameList", "ValueList", "ScadaReadTimeUnixMs", "ActualTimeUtc", "TypeName", "Version"}
    shape_ok = all(need <= set(e) for e in emitted)

    result = {
        "ticks": ticks,
        "emits": len(emitted),
        "async_delta": plant.async_delta,
        "every_emit_ge_delta": gaps_ok,
        "async_gated_fewer_than_ticks": gated,
        "matches_reference_async_filter": matches_reference,
        "flux_shape_ok": shape_ok,
        "PASS": gaps_ok and gated and matches_reference and shape_ok,
        "sample_emits": emitted[:3],
    }
    (OUT / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in
                      ("ticks", "emits", "async_delta", "every_emit_ge_delta",
                       "async_gated_fewer_than_ticks", "matches_reference_async_filter",
                       "flux_shape_ok", "PASS")}, indent=2))


if __name__ == "__main__":
    main()
