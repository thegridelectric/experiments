"""EDD witness: dev-broker record broadcasts — the minting act's wire half.

`broadcast_record` (the `gwwf broadcast-record` path) publishes stored
records from the gridworks-weather DB onto the bus. Two taps bind on
weathermic_tx exactly as delivery.md "Broadcast binding shape" specifies:

- the BUNDLE record on the tail-LESS key
  (`rjb.d1-weather.weather.gw-weather-forecast-bundle-gt`), and
- the location record on its own alias as the radio tail.

PASS = each tap decodes its record byte-equal through the vendored
snapshot codec, on the expected routing key.

Run from the gwwf venv (dev rabbit + seeded local postgres up):

    cd ~/GridWorks/gridworks-weather-forecast
    uv run python ../experiments/2026-08-12-gwwf-record-broadcast/witness.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import dotenv
import gwwf

dotenv.load_dotenv(Path(gwwf.__file__).parents[2] / ".env")

from gwbase.actor_base import ActorBase  # noqa: E402
from gwbase.config import ServiceSettings  # noqa: E402
from gwbase.transport_encoding import RoutingEnvelope, TransportClass  # noqa: E402

from gwwf.config import GwwfSettings  # noqa: E402
from gwwf.db.session import SessionLocal  # noqa: E402
from gwwf.names import MILLINOCKET, MILLINOCKET_FORECAST_NWS_HOURLY  # noqa: E402
from gwwf.record_broadcast import broadcast_record, load_record  # noqa: E402
from gwwf.sema.codec import SemaCodec  # noqa: E402
from gwwf.sema.types import (  # noqa: E402
    GwWeatherForecastBundleGt,
    GwWeatherLocationGt,
)


def wait_for(predicate, seconds: float, desc: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(desc)


class RecordTap(ActorBase):
    """Binds one record type's broadcast key; decodes via the snapshot."""

    def __init__(
        self,
        settings: ServiceSettings,
        publisher_alias: str,
        expect: type,
        radio_channel: str | None,
    ) -> None:
        super().__init__(settings=settings)
        self._publisher_alias = publisher_alias
        self._expect = expect
        self._radio_channel = radio_channel
        self.codec = SemaCodec()
        self.witnessed = None
        self.witnessed_key: str | None = None

    def local_rabbit_startup(self) -> None:
        self.subscribe_broadcast(
            from_alias=self._publisher_alias,
            from_class=TransportClass.WeatherForecastService,
            type_name=self._expect.type_name_value(),
            radio_channel=self._radio_channel,
        )

    def dispatch_message(self, *, envelope: RoutingEnvelope, body: bytes) -> None:
        self.witnessed = self.codec.from_dict(json.loads(body), expect=self._expect)
        self.witnessed_key = envelope.routing_key


def main() -> int:
    settings = GwwfSettings()
    bundle_tap = RecordTap(
        ServiceSettings(
            rabbit=settings.rabbit,
            service_alias="d1.wx.rectap1",
            service_name="gwwf-record-witness-bundle",
        ),
        publisher_alias=settings.service_alias,
        expect=GwWeatherForecastBundleGt,
        radio_channel=None,
    )
    location_tap = RecordTap(
        ServiceSettings(
            rabbit=settings.rabbit,
            service_alias="d1.wx.rectap2",
            service_name="gwwf-record-witness-location",
        ),
        publisher_alias=settings.service_alias,
        expect=GwWeatherLocationGt,
        radio_channel=MILLINOCKET,
    )

    bundle_tap.start()
    location_tap.start()
    try:
        wait_for(lambda: bundle_tap.consuming, 8, "bundle tap consuming")
        wait_for(lambda: location_tap.consuming, 8, "location tap consuming")
        time.sleep(0.5)  # binds are issued as consuming starts

        with SessionLocal() as session:
            stored_bundle = load_record(
                session, "bundle", MILLINOCKET_FORECAST_NWS_HOURLY
            )
            stored_location = load_record(session, "location", MILLINOCKET)
            bundle_key = broadcast_record(
                settings, session, "bundle", MILLINOCKET_FORECAST_NWS_HOURLY
            )
            location_key = broadcast_record(
                settings, session, "location", MILLINOCKET
            )

        print(f"bundle published on:   {bundle_key}")
        print(f"location published on: {location_key}")

        wait_for(lambda: bundle_tap.witnessed is not None, 8, "bundle decoded")
        wait_for(lambda: location_tap.witnessed is not None, 8, "location decoded")

        checks = [
            ("bundle byte-equal", bundle_tap.witnessed == stored_bundle),
            ("bundle key tail-less", bundle_key.endswith("gw-weather-forecast-bundle-gt")),
            ("bundle key as witnessed", bundle_tap.witnessed_key == bundle_key),
            ("location byte-equal", location_tap.witnessed == stored_location),
            ("location tail = alias", location_key.endswith(f".{MILLINOCKET}")),
            ("location key as witnessed", location_tap.witnessed_key == location_key),
        ]
        failed = [name for name, ok in checks if not ok]
        for name, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if failed:
            print(f"WITNESS FAIL: {failed}")
            return 1
        print("WITNESS PASS")
        return 0
    finally:
        bundle_tap.stop()
        location_tap.stop()


if __name__ == "__main__":
    sys.exit(main())
