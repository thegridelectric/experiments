# realtime-units-elm-check, 2026-10-28

> What this is: the page check for OPS-622's real-time-units slice. Does
> the local frontend show elm's live snapshot in the units elm's
> `layout.lite` 013 declares? Verdict: PASS, in `instances/`.

## Why

The real-time page decided units by channel name, so on elm's 013 layout
(temperatures in CelsiusTimes100, where the page assumed
WaterTempCTimes1000) hp-ewt showed 37.4 F and a zone 1.8 F. The slice
converts every reading through the unit the house's layout declares.
The spoke's bar: hp-ewt, hp-lwt, dist-swt, tank1-depth1 and zone1 read
within a tenth of a degree of the same channels in the visualizer, and
the pump table shows elm's secondary pump.

## Setup

The dev-stack recipe, with the web-backend and the journalkeeper on
`tsdb_tap` and the tap broker. Nothing deployed was touched; the fleet
stream was read through the analyst login.

- `tsdb_tap` refreshed for elm: its `layouts` row, 235 `reading_channels`
  rows and the `layout.lite` messages since 2026-10-20 pulled from prod
  and swapped in (the copy of 2026-10-24 had elm's 011 layout of
  2026-08-16).
- gridworks-web-backend `main`: API on 8000 against `tsdb_tap`; gateway
  on 8100 against the tap broker as `gw.analyst`, through
  `run_gateway_on_tap.py`.
- gridworks-journalkeeper `main` on the tap broker into `tsdb_tap`.
- gridworks-web-frontend `jm/realtime-units` at `f21a0f2` plus the
  uncommitted step 4 (the page converts through the layout's units;
  committed next as "the real-time page converts through the layout's
  units"), vite on 5173.
- `harness/check.mjs` logs in as `devrun-admin`, opens
  `/real-time/hw1.isone.me.versant.keene.elm/`, captures the websocket
  snapshot and the DOM, and screenshots the page. `harness/expected.ts`
  converts the captured snapshot through the frontend's own modules and
  checks each string is in the DOM. `harness/compare.mts` reads the
  bundle through the API for the ten minutes before the snapshot and
  converts the newest journal sample with the visualizer's converter.

## Found

PASS. At the 18:50:30Z snapshot every value the page shows equals the
frontend's conversion of the raw value through elm's declared unit:

| channel | raw | unit | shown |
|---|---|---|---|
| hp-ewt | 5364 | CelsiusTimes100 | 128.6°F |
| hp-lwt | 6178 | CelsiusTimes100 | 143.2°F |
| dist-swt | 5123 | CelsiusTimes100 | 124.2°F |
| tank1-depth1 | 10391 | FahrenheitX100 | 103.9°F |
| zone1-living-kitchen-temp | 1778 | CelsiusTimes100 | 64.0°F |
| zone1-living-kitchen-set | 1667 | CelsiusTimes100 | 62.0°F |
| primary-flow | 576 | GpmTimes100 | 5.8 GPM |
| secondary-flow | 655 | GpmTimes100 | 6.5 GPM |
| secondary-pump-pwr | 13 | PowerW | 13.0 W |
| hp-odu-pwr | 5848 | PowerW | 5.85 kW |

The visualizer's converter gives the same number for the same journal
sample on every channel. hp-ewt differed in the comparison run (127.6
against 128.6) because the journal's newest sample (5313 at 18:50:31Z)
is 26 s younger than the one in the snapshot (5364, read 18:50:05Z); the
two raw values convert to the two displayed values. The pump table has
the Secondary row because elm's layout declares `secondary-flow`.
Channels with no display value are the relays, the micro-volt and
0-10 V channels, the flow hertz and the heat calls, none of which the
page shows as a number.

## Timeline

ET, 2026-10-28.

- 14:37 API, gateway, journalkeeper and vite started. The gateway's
  queue declaration was refused (`web.gateway.*` under `gw.analyst`).
- 14:38 Gateway restarted through `run_gateway_on_tap.py`; consuming.
- 14:40 First page check: 95 readings in the snapshot, every expected
  string in the DOM.
- 14:47 The journalkeeper's process found connected to the Timescale
  cloud port instead of to `tsdb_tap`; stopped. See "Analysis notes".
- 14:48 Journalkeeper restarted from a clean shell; connections to the
  tap broker and port 5433 only.
- 14:50 Second page check at the 18:50:30Z snapshot; elm's readings in
  `tsdb_tap` (694 rows) from 14:52; the bundle comparison run.
- 14:51 Stack down, both `.env` files restored to their 14:20 content.

## Analysis notes

- **The journalkeeper ran against production for about ten minutes
  (18:37 to 18:47 UTC).** The shell that started it had sourced
  `experiments/.env` to read the tap URL, and that file's `GJK_DB_URL`
  is the prod writer login; the environment outranks the repo's `.env`.
  Checked on prod afterwards: the window's messages are snapshots,
  power and reports only, there are no duplicate `(channel_id,
  timestamp)` readings, both tables have unique keys that refuse a
  second copy of a row the prod journalkeeper writes, and no layout or
  channel rows were created in the window. Recorded in the recipe's
  "Things that bit".
- The page check is of the frontend's conversion against its own
  modules and the visualizer's converter, with the human eye on the
  screenshot. It does not read values off the visualizer's plot.
- The bundle comparison converts power to kW, so `secondary-pump-pwr`
  reads 0.013 there and 13.0 W on the page.

## Folder contents & experimental method

The snapshot and the layout came from the running system: the snapshot
is elm's live `snapshot.spaceheat` as the gateway forwarded it over the
page's websocket, and the layout is elm's `layout.lite` 013 as the API's
installation summary served it from `tsdb_tap`. The journal samples in
the comparison came from `tsdb_tap`, written by the journalkeeper from
the tap broker during the run; they are also in the production journal.
The pulls are copies of production rows.

- `harness/check.mjs`: the page check (playwright-core, the installed
  Chrome). Needs `DEVRUN_API_USER` and `DEVRUN_API_PASSWORD` in the
  environment and a scratch folder with `playwright-core` installed.
- `harness/expected.ts`, `harness/compare.mts`: the two comparisons, run
  with `tsx` from the frontend's directory so its modules resolve.
- `run_gateway_on_tap.py`: the gateway with the analyst queue prefix.
- `logs/snapshot-elm.json`: the captured snapshot (wire form, untouched).
- `logs/layout-elm.json` (not in the folder; the saved copy was empty):
  elm's `layout.lite` 013 as the API's installation summary serves it,
  saved by hand before `expected.ts` runs. Re-fetch it from the API.
- `logs/check-elm.out`, `logs/check-elm-2.out`: the DOM of the two page
  checks; `logs/compare-elm.out`: the bundle comparison.
- `logs/gateway.log`, `logs/vite.log`: service output. The API log was
  dropped because it echoes credentials.
- `pulls/*-regen.csv` (gitignored): elm's `layouts`, `reading_channels`
  and `layout.lite` rows from prod.
- `instances/realtime-units-elm-check-gw.experiment.run-001.json`: the
  verdict.

Regenerate, from the umbrella dir with the stack up as in Setup:

    set -a; . experiments/.env; set +a   # in a shell that starts NO service
    E=experiments/2026-10-28-realtime-units-elm-check
    psql "$DB_ANALYST_URL" -c "\copy (select * from gridworks.layouts where from_alias like '%elm%') to '$E/pulls/elm_layouts-regen.csv' with (format csv, header)"
    psql "$DB_ANALYST_URL" -c "\copy (select * from gridworks.reading_channels where terminal_asset_alias like '%elm%') to '$E/pulls/elm_reading_channels-regen.csv' with (format csv, header)"
    psql "$DB_ANALYST_URL" -c "\copy (select * from gridworks.messages where message_type_name='layout.lite' and from_alias like '%elm%' and timestamp >= '2026-10-20') to '$E/pulls/elm_layout_lite-regen.csv' with (format csv, header)"
    (cd <scratch> && DEVRUN_API_USER=… DEVRUN_API_PASSWORD=… node $PWD/$E/harness/check.mjs hw1.isone.me.versant.keene.elm $PWD/$E/logs > $E/logs/check-elm.out)
    (cd gridworks-web-frontend && tsx $E/harness/expected.ts $E/logs/snapshot-elm.json $E/logs/layout-elm.json $E/logs/check-elm.out)
    (cd gridworks-web-frontend && tsx $E/harness/compare.mts $E/logs/snapshot-elm.json $E/logs/check-elm.out <token>)

A re-run captures a new snapshot and is a new dataset.
