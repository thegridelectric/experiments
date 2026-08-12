# gwwf record broadcasts — dev-broker witness

The minting act's wire half (`gwwf broadcast-record`, stand-up-weather-forecast
build step 7): stored records publish once onto the bus; the bundle
broadcast is tail-less, every other record rides its own name as the
radio tail; taps decode byte-equal through the vendored snapshot.

Reproduce (dev rabbit + seeded local postgres up):

```sh
cd ~/GridWorks/gridworks-weather-forecast
uv run python ../experiments/2026-08-12-gwwf-record-broadcast/witness.py
```

## Logbook

- 2026-08-12 PASS (first run after seeding the local dev DB — the
  fresh post-r2 schema had never been seeded locally). Six checks:
  bundle byte-equal, bundle key tail-less
  (`rjb.d1-weather.weather.gw-weather-forecast-bundle-gt`), bundle key
  as witnessed, location byte-equal, location tail = alias
  (`…gw-weather-location-gt.us.me.millinocket`), location key as
  witnessed.
