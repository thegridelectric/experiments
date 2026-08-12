"""EDD witness: fast-record EmissionScheduler run on the dev broker.

The scheduler is record-driven, so no time is mocked: witness channel
records carry second-scale schedules (observations 20s/0, forecasts
20s/10) and scripted fetchers play a fixed scenario through gwwf's
real actor plumbing against gw-dev-rabbit. A tap bound to the three
stream slugs plus the glitch broadcast decodes everything through the
vendored snapshot and asserts:

  1. a real observation publishes on the location slug;
  2. a slot with nothing new stays silent (exact message counts);
  3. recovery replays the missed grid point interpolated
     (Interpolated: true, linear value);
  4. Live forecasts land one-per-BUNDLE with values laid on a
     NON-uniform slice grid ([300, 600, 300]);
  5. losing the live source downgrades to Stored with a glitch.

Run from the gwwf venv (dev broker must be up):

    cd ~/GridWorks/gridworks-weather-forecast
    uv run python ../experiments/2026-08-11-gwwf-scheduler-witness/witness.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import dotenv
import gwwf

dotenv.load_dotenv(Path(gwwf.__file__).parents[2] / ".env")

from gwbase.actor_base import ActorBase  # noqa: E402
from gwbase.config import ServiceSettings  # noqa: E402
from gwbase.gridworks_actor import GridworksActor  # noqa: E402
from gwbase.transport_encoding import RoutingEnvelope, TransportClass  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

from gwwf.config import GwwfSettings  # noqa: E402
from gwwf.grid import next_slot, s_to_iso  # noqa: E402
from gwwf.nws import HourlyForecastProduct  # noqa: E402
from gwwf.scheduler import (  # noqa: E402
    EmissionScheduler,
    ForecastStream,
    ObservationStream,
    WeatherMessage,
)
from gwwf.sema.codec import SemaCodec  # noqa: E402
from gwwf.sema.enums import Gw1Quantity, Gw1Unit, LogLevel  # noqa: E402
from gwwf.sema.property_format import LeftRightDot  # noqa: E402
from gwwf.sema.types import (  # noqa: E402
    Glitch,
    GwWeatherChannelGt,
    GwWeatherForecast,
    GwWeatherForecastBundleGt,
    GwWeatherForecastChannelGt,
    GwWeatherObservation,
)

_lrd: TypeAdapter[LeftRightDot] = TypeAdapter(LeftRightDot)
LOCATION = _lrd.validate_python("d1.witness")
TEMP = _lrd.validate_python("d1.witness.temperature")
WIND = _lrd.validate_python("d1.witness.windspeed")
TEMP_FC = _lrd.validate_python("d1.witness.temperature.forecast.fake.hourly")
WIND_FC = _lrd.validate_python("d1.witness.windspeed.forecast.fake.hourly")
BUNDLE_NAME = _lrd.validate_python("d1.witness.forecast.fake.hourly")

OBS_PERIOD_S, OBS_OFFSET_S = 20, 0
FC_PERIOD_S, FC_OFFSET_S = 20, 10
SOURCE_PERIOD_S = 300
TIMEOUT_S = 150


def observation_channel(name: str, quantity: Gw1Quantity, unit: Gw1Unit):
    return GwWeatherChannelGt(
        name=name,
        display_name=f"witness {name}",
        quantity=quantity,
        unit=unit,
        location_alias=LOCATION,
        emit_period_s=OBS_PERIOD_S,
        emit_offset_s=OBS_OFFSET_S,
        start="2026-08-11T00:00:00Z",
        id=str(uuid.uuid4()),
    )


def forecast_channel(name: str, target: str, durations: list[int]):
    return GwWeatherForecastChannelGt(
        name=name,
        target_channel_name=target,
        forecaster="fake.model",
        method="fake.method",
        total_slices=len(durations),
        slice_duration_s_list=durations,
        forecast_duration_minutes=sum(durations) // 60,
        emit_period_s=FC_PERIOD_S,
        emit_offset_s=FC_OFFSET_S,
        start="2026-08-11T00:00:00Z",
        id=str(uuid.uuid4()),
    )


def witness_bundle() -> GwWeatherForecastBundleGt:
    temp_obs = observation_channel(
        TEMP, Gw1Quantity.Temperature, Gw1Unit.FahrenheitX100
    )
    wind_obs = observation_channel(
        WIND, Gw1Quantity.WindSpeed, Gw1Unit.MilesPerHourX1000
    )
    return GwWeatherForecastBundleGt(
        name=BUNDLE_NAME,
        display_name="witness bundle",
        location_alias=LOCATION,
        temp_forecast_channel=forecast_channel(TEMP_FC, TEMP, [300, 600, 300]),
        temp_observation_channel=temp_obs,
        wind_speed_forecast_channel=forecast_channel(
            WIND_FC, WIND, [300, 600, 300]
        ),
        wind_speed_observation_channel=wind_obs,
        start="2026-08-12T00:00:00Z",
        id=str(uuid.uuid4()),
    )


def observation(epoch_s: int, temp: int, wind: int) -> GwWeatherObservation:
    return GwWeatherObservation(
        location_alias=LOCATION,
        observation_time=s_to_iso(epoch_s),
        interpolated=False,
        temp_channel_name=TEMP,
        temp_value=temp,
        wind_speed_channel_name=WIND,
        wind_speed_value=wind,
    )


class ScriptedFetch:
    """Returns/raises the scripted items in order; repeats the last."""

    def __init__(self, items: list) -> None:
        self._items = list(items)

    def next(self):
        item = self._items.pop(0) if len(self._items) > 1 else self._items[0]
        if isinstance(item, Exception):
            raise item
        return item


class WitnessActor(GridworksActor):
    """gwwf's actor plumbing driving a fast-record scheduler."""

    def __init__(self, settings: GwwfSettings, scheduler_factory) -> None:
        super().__init__(
            settings=settings,
            transport_class=TransportClass.WeatherForecastService,
            my_super_alias=settings.my_super_alias,
            my_time_coordinator_alias=settings.my_time_coordinator_alias,
        )
        self.scheduler = scheduler_factory(self._publish_stream, self._raise_glitch)

    def process_message(self, *, envelope: RoutingEnvelope, body: bytes) -> None:
        pass

    def tick(self) -> None:
        self.scheduler.run_pending(int(time.time()))

    def _publish_stream(self, message: WeatherMessage, radio_channel: str) -> None:
        envelope = self.broadcast_envelope(
            type_name=message.type_name, radio_channel=radio_channel
        )
        self.send(envelope=envelope, body=json.dumps(message.to_dict()).encode("utf-8"))

    def _raise_glitch(self, level: LogLevel, summary: str, details: str) -> None:
        glitch = Glitch(
            from_g_node_alias=self.alias,
            node="scheduler",
            type=level,
            summary=summary,
            details=details,
            created_ms=int(time.time() * 1000),
        )
        envelope = self.broadcast_envelope(type_name=glitch.type_name)
        self.send(envelope=envelope, body=json.dumps(glitch.to_dict()).encode("utf-8"))


class WitnessTap(ActorBase):
    """Binds the three stream slugs + the glitch broadcast; decodes all."""

    def __init__(self, settings: ServiceSettings, publisher_alias: str) -> None:
        super().__init__(settings=settings)
        self._publisher_alias = publisher_alias
        self.codec = SemaCodec()
        self.observations: list[GwWeatherObservation] = []
        self.forecasts: list[GwWeatherForecast] = []
        self.glitches: list[Glitch] = []

    def local_rabbit_startup(self) -> None:
        for type_name, radio in [
            (GwWeatherObservation.type_name_value(), LOCATION),
            (GwWeatherForecast.type_name_value(), BUNDLE_NAME),
            (Glitch.type_name_value(), None),
        ]:
            self.subscribe_broadcast(
                from_alias=self._publisher_alias,
                from_class=TransportClass.WeatherForecastService,
                type_name=type_name,
                radio_channel=radio,
            )

    def dispatch_message(self, *, envelope: RoutingEnvelope, body: bytes) -> None:
        decoded = self.codec.from_dict(json.loads(body))
        if isinstance(decoded, GwWeatherObservation):
            self.observations.append(decoded)
        elif isinstance(decoded, GwWeatherForecast):
            self.forecasts.append(decoded)
        elif isinstance(decoded, Glitch):
            self.glitches.append(decoded)
        print(f"  tap ← {envelope.routing_key}")


def wait_for(predicate, seconds: float, desc: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(desc)


def main() -> int:
    t0 = int(time.time())
    s1 = next_slot(t0 + 1, OBS_PERIOD_S, OBS_OFFSET_S)  # first obs slot after boot
    obs1 = observation(s1 - 5, temp=6000, wind=3000)
    obs2 = observation(s1 + 35, temp=6900, wind=4800)  # slot s1+20 missed → replay
    obs_fetch = ScriptedFetch([obs1, obs1, obs2])

    p0 = (t0 // SOURCE_PERIOD_S) * SOURCE_PERIOD_S
    temps = [50 + i for i in range(40)]
    winds = [5 + i for i in range(40)]
    product = HourlyForecastProduct(
        update_time=s_to_iso(p0),
        generated_at=s_to_iso(p0),
        first_slice_start=s_to_iso(p0),
        period_s=SOURCE_PERIOD_S,
        temperature_f=temps,
        wind_speed_mph=winds,
    )
    product_fetch = ScriptedFetch([product, RuntimeError("live source down")])

    bundle = witness_bundle()

    def scheduler_factory(publish, raise_glitch) -> EmissionScheduler:
        return EmissionScheduler(
            observation_streams=[
                ObservationStream(
                    channels=[
                        bundle.temp_observation_channel,
                        bundle.wind_speed_observation_channel,
                    ],
                    fetch=lambda: obs_fetch.next(),
                )
            ],
            forecast_streams=[
                ForecastStream(
                    bundle=bundle,
                    fetch=lambda slices: product_fetch.next(),
                    temp_scale=100,
                    wind_speed_scale=1000,
                )
            ],
            publish=publish,
            raise_glitch=raise_glitch,
            now_s=t0,
        )

    pub_settings = GwwfSettings()
    pub = WitnessActor(pub_settings, scheduler_factory)
    tap = WitnessTap(
        ServiceSettings(
            rabbit=pub_settings.rabbit,
            service_alias="d1.witness.tap",
            service_name="gwwf-scheduler-witness",
        ),
        publisher_alias=pub_settings.service_alias,
    )

    tap.start()
    pub.start()
    try:
        wait_for(lambda: tap.consuming, 8, "tap consuming")
        wait_for(lambda: pub.consuming, 8, "publisher consuming")
        time.sleep(0.5)  # slug binds land as consuming starts

        def scenario_complete() -> bool:
            reals = [o for o in tap.observations if not o.interpolated]
            filled = [o for o in tap.observations if o.interpolated]
            fidelities = {f.fidelity.value for f in tap.forecasts}
            downgrades = [g for g in tap.glitches if "downgrade" in g.summary]
            return (
                len(reals) >= 2
                and len(filled) >= 1
                and {"Live", "Stored"} <= fidelities
                and len(downgrades) >= 1
            )

        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline and not scenario_complete():
            pub.tick()
            time.sleep(0.25)
    finally:
        pub.stop()
        tap.stop()

    reals = [o for o in tap.observations if not o.interpolated]
    filled = [o for o in tap.observations if o.interpolated]
    live = [f for f in tap.forecasts if f.fidelity.value == "Live"]
    stored = [f for f in tap.forecasts if f.fidelity.value == "Stored"]
    downgrades = [g for g in tap.glitches if "downgrade" in g.summary]

    print(f"\nreal observations: {[o.observation_time for o in reals]}")
    print(f"interpolated:      {[o.observation_time for o in filled]}")
    print(f"live forecasts:    {len(live)}  stored: {len(stored)}")
    print(f"downgrade glitches: {[g.summary for g in downgrades]}")

    assert len(reals) == 2, f"expected exactly 2 real observations, got {len(reals)}"
    assert len(filled) == 1, f"expected exactly 1 interpolated fill, got {len(filled)}"
    fill = filled[0]
    assert fill.observation_time == s_to_iso(s1 + 20)
    # Linear between (s1-5, 6000) and (s1+35, 6900) at s1+20:
    # 6000 + 900*25/40 = 6562.5 → 6562 (round-half-even).
    assert fill.temp_value == 6562, fill.temp_value
    assert fill.wind_speed_value == 4125, fill.wind_speed_value  # 3000 + 1800*25/40

    assert live, "no Live forecast witnessed"
    message = live[0]
    assert message.bundle_name == BUNDLE_NAME
    first_s = int(datetime.fromisoformat(message.first_slice_start).timestamp())
    starts = [first_s, first_s + 300, first_s + 900]
    expected_temps = [(50 + (s - p0) // SOURCE_PERIOD_S) * 100 for s in starts]
    expected_winds = [(5 + (s - p0) // SOURCE_PERIOD_S) * 1000 for s in starts]
    assert message.temp_values == expected_temps, (message.temp_values, expected_temps)
    assert message.wind_speed_values == expected_winds
    assert len(stored) >= 1 and len(downgrades) >= 1

    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
