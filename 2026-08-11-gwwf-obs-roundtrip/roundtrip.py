"""EDD witness: dev-broker gw.weather.observation round trip.

gwwf's publish path (a GridworksActor with TransportClass
WeatherForecastService, gwwf settings + identity) broadcasts one
gw.weather.observation with the location alias as the radio channel;
a tap binds ONLY that slug on weathermic_tx and decodes the body
through the gwwf vendored snapshot codec. PASS = the decoded instance
equals the published one, on the expected routing key.

Run from the gwwf venv (the harness imports gwwf + its snapshot):

    cd ~/GridWorks/gridworks-weather-forecast
    uv run python ../experiments/2026-08-11-gwwf-obs-roundtrip/roundtrip.py

Channel names are the design's (the .gt channel records land at build
step 4; until then the names here mirror vocabulary.md).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import dotenv
import gwwf

dotenv.load_dotenv(Path(gwwf.__file__).parents[2] / ".env")

from gwbase.actor_base import ActorBase  # noqa: E402
from gwbase.config import ServiceSettings  # noqa: E402
from gwbase.gridworks_actor import GridworksActor  # noqa: E402
from gwbase.transport_encoding import RoutingEnvelope, TransportClass  # noqa: E402

from gwwf.config import GwwfSettings  # noqa: E402
from gwwf.names import (  # noqa: E402
    MILLINOCKET,
    MILLINOCKET_TEMPERATURE,
    MILLINOCKET_WINDSPEED,
)
from gwwf.sema.codec import SemaCodec  # noqa: E402
from gwwf.sema.types import GwWeatherObservation  # noqa: E402


def wait_for(predicate, seconds: float, desc: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(desc)


class WitnessPublisher(GridworksActor):
    """gwwf's publish path, without the legacy NWS poller."""

    def __init__(self, settings: GwwfSettings) -> None:
        super().__init__(
            settings=settings,
            transport_class=TransportClass.WeatherForecastService,
            my_super_alias=settings.my_super_alias,
            my_time_coordinator_alias=settings.my_time_coordinator_alias,
        )

    def process_message(self, *, envelope: RoutingEnvelope, body: bytes) -> None:
        pass


class SlugBoundTap(ActorBase):
    """Binds only the location slug on weathermic_tx; decodes via snapshot."""

    def __init__(self, settings: ServiceSettings, publisher_alias: str) -> None:
        super().__init__(settings=settings)
        self._publisher_alias = publisher_alias
        self.codec = SemaCodec()
        self.witnessed: GwWeatherObservation | None = None
        self.witnessed_key: str | None = None

    def local_rabbit_startup(self) -> None:
        self.subscribe_broadcast(
            from_alias=self._publisher_alias,
            from_class=TransportClass.WeatherForecastService,
            type_name=GwWeatherObservation.type_name_value(),
            radio_channel=MILLINOCKET,
        )

    def dispatch_message(self, *, envelope: RoutingEnvelope, body: bytes) -> None:
        self.witnessed = self.codec.from_dict(
            json.loads(body), expect=GwWeatherObservation
        )
        self.witnessed_key = envelope.routing_key


def main() -> int:
    pub_settings = GwwfSettings()
    pub = WitnessPublisher(pub_settings)
    tap = SlugBoundTap(
        ServiceSettings(
            rabbit=pub_settings.rabbit,
            service_alias="d1.wx.tap",
            service_name="gwwf-obs-roundtrip",
        ),
        publisher_alias=pub_settings.service_alias,
    )

    obs = GwWeatherObservation(
        location_alias=MILLINOCKET,
        observation_time=datetime.now(UTC)
        .replace(minute=0, second=0, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        interpolated=False,
        temp_channel_name=MILLINOCKET_TEMPERATURE,
        temp_value=7268,
        wind_speed_channel_name=MILLINOCKET_WINDSPEED,
        wind_speed_value=4500,
    )

    tap.start()
    pub.start()
    try:
        wait_for(lambda: tap.consuming, 8, "tap consuming")
        wait_for(lambda: pub.consuming, 8, "publisher consuming")
        time.sleep(0.5)  # the slug bind is issued as consuming starts

        envelope = pub.broadcast_envelope(
            type_name=obs.type_name, radio_channel=MILLINOCKET
        )
        print(f"publishing on: {envelope.routing_key}")
        diag = pub.send(
            envelope=envelope, body=json.dumps(obs.to_dict()).encode("utf-8")
        )
        print(f"send diagnostic: {diag}")

        wait_for(lambda: tap.witnessed is not None, 8, "tap decoded the observation")
    finally:
        pub.stop()
        tap.stop()

    assert tap.witnessed is not None
    assert tap.witnessed.to_dict() == obs.to_dict(), "decoded != published"
    print(f"witnessed on:   {tap.witnessed_key}")
    print(json.dumps(tap.witnessed.to_dict(), indent=2))
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
