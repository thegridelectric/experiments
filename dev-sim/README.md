# dev-sim

What this is: the dev simulation as one Pod for `podman kube play`. Two
simulated Beech houses (a scada, a plant and an LTN each) run with the
FLO, the price service, the market maker, the weather service, the GNode
registry, the journal and the web app, all in universe `d1`, run `d1__1`. It is a
standing stack and has no date. The record of its first runs is
`../2026-11-11-beech-sim-compose/`.

## Run

    ./run.sh
    ./stop.sh

`run.sh` builds the images and plays `pod.yaml`. It needs Podman, the
ISO-NE account in `./price.env` and `./mm.env` (gitignored; `pod.yaml`'s
header gives the names), and the bruce volume filled once per house
shape (the command is in `pod.yaml`'s header).

`sources.txt` names the commit of every repo the pod is built from.
`fetch-sources.sh` clones each sibling checkout into `./.sources/` at
that commit, and the builds and `houses.sh` read only `./.sources/`, so
a sibling's branch and working tree do not matter and are not touched.
Each built image has its commit as the label `gw.source`. To move a
pin, change its line and run `./run.sh`. `run.sh` stops before it
builds when the committed houses differ from what the pins give; a
change to the `tlayouts`, `gridworks-scada` or `grid-node-registry` pin
needs `./houses.sh` and a read of its diff. The registry is the one
image that is pulled: `pod.yaml` names
`ghcr.io/thegridelectric/grid-node-registry` at the commit `sources.txt`
has, and `run.sh` stops when the two differ.

Three ports are published on the host: the web app on 5173
(`http://localhost:5173/gridworks-web-frontend/`, login `beech` /
`beech`), the realtime gateway on 8100, and the journal database on
5434. Everything else is on the pod's localhost.

`stop.sh` drops the journal database and the registry's database with
the pod. `./eventstore`, `./events-beech1`, `./events-beech2` and the
bruce volume stay.

## The houses

`beech1/` and `beech2/` are twins: one spec, the real Beech's, simulated
at two aliases, `d1.isone.me.versant.keene.beech1` and `…keene.beech2`.
The layouts differ only in identity. beech1 runs `AllTanks` and beech2
runs `BufferOnly`, so the two variants can be compared, and the variant
is only in the operational params. Both LTNs bid into the one market
maker, `d1.isone.me.versant.keene`, so the two houses share a market.

Nothing here makes a house. tlayouts writes both at the commit in
`sources.txt`, with the GNodeIds the registry's dev seed issues.
`houses.sh` copies each layout byte for byte, sets beech2's storage mode
by authoring its params again through `OperationalParams`, writes each
`ta.deed`, and copies the FLO's GNode from the registry's export. The
result is committed.

The web app names the houses `beech-at` and `beech-buf`. Those are the
DisplayNames of the two TerminalAssets in the registry's dev seed. The
pod runs the registry, the keeper writes `g_nodes` from its
`g.node.forest`, and the web API reads `g_nodes`.

## Files

- `run.sh`: builds the images (cached layers; a later run rebuilds an
  image only when its files changed) and starts the pod.
- `build.sh`: the image builds, on their own.
- `package.sh`: zips the images this tree builds and the files another
  box needs to run the sim, without the sibling checkouts.
  `./package.sh --dry-run` lists them. The zip's `run.sh` loads those
  images, pulls Rabbit, Mosquitto, Postgres and Timescale, and plays
  the pod. It holds `price.env` and `mm.env`.
- `stop.sh`: stops the pod. The journal database and the registry's
  database go with it. `./eventstore`, `./events-beech1`,
  `./events-beech2` and the bruce volume stay.
- `pod.yaml`: the stack as one Pod, for
  `podman kube play`: two scada+ta pairs (beech1 at AllTanks and
  beech2 at BufferOnly) and an LTN for each, the FLO they ask, the price
  service the LTNs read (`gwpf rabbit` and `gwpf api`, one image), the
  market maker they clear against (`gwmm rabbit`), the weather service
  they read (`gwwf rabbit` and `gwwf api`, its own Postgres on
  pod port 5436, dev records minted at each start), the registry
  (`gnr rabbit` as `d1.gnr`, its own Postgres on pod port 5435, seeded
  with the dev universe at each start), and the journal: the
  ear writing `./eventstore` (`ear listen --no-s3`), TimescaleDB
  published on host port 5434, the keeper, and the web app on host
  port 5173 (`http://localhost:5173/gridworks-web-frontend/`, login
  `beech` / `beech`) with its realtime gateway on host port 8100. The
  FLO runs under
  memory and CPU limits.
- `price.Dockerfile`, `price.Dockerfile.dockerignore`: the price
  service's image, built with a `gridworks-price-forecast` checkout as
  its context. `./price.env` (gitignored) holds the ISO-NE account.
- `mm.Dockerfile`, `mm.Dockerfile.dockerignore`: the market maker's
  image, built with a `gridworks-marketmaker` checkout as its context.
  `./mm.env` (gitignored) holds the ISO-NE account. The house's
  operational params name this maker, `d1.isone.me.versant.keene`.
- `journal.Dockerfile`, `journal.Dockerfile.dockerignore`: the journal
  keeper's image, built with a `gridworks-journalkeeper` checkout as
  its context. `journal_boot.py` creates the dev roles, the
  `gridworks` tables and the web login before the keeper starts.
- `weather.Dockerfile`, `weather.Dockerfile.dockerignore`: the weather
  service's image, built from
  the `gridworks-weather-forecast` checkout.
  The scada and the LTN read `http://127.0.0.1:8531/d1-weather`.
- `ear.Dockerfile`, `ear.Dockerfile.dockerignore`: the ear's image,
  built from the `gridworks-ear` checkout.
  With `--no-s3` it writes each message under `./eventstore`.
- `web.Dockerfile`, `web.Dockerfile.dockerignore`: the web backend's
  image, built with a `gridworks-web-backend` checkout as its context.
  `python -m api` reads the journal; `python -m gateway` serves the
  realtime page.
- `frontend.Dockerfile`, `frontend.Dockerfile.dockerignore`: the web
  frontend's image, built with a `gridworks-web-frontend` checkout as
  its context. Vite proxies `/api` to the API in the pod. At start the
  container reads each house's GNode alias and `WeatherBundleName` from
  `./beech1` and `./beech2` into `VITE_HOUSE_WEATHER_BUNDLES`, so
  the weather panel draws the bundle that house's operational params
  name.
- `flo.Dockerfile`, `flo.Dockerfile.dockerignore`: the FLO's image, built
  with a `gridworks-flo` checkout as its context and the sibling
  `optimal-flexibility` as the `bruce` context.
- `flo_matrix.py`: fills the bruce volume with the house's transition
  matrices, one per seasonal storage mode, run once in the FLO's image.
  Beech's took 535 s (AllTanks) and 1105 s (BufferOnly) on one core,
  peaking at 452 MB.
- `flo/g.node.gt.json`: the FLO's identity, `d1.flo`, a copy of the
  registry's export. Written by `houses.sh`.
- `sources.txt`, `fetch-sources.sh`: the commit of each repo the pod is
  built from, and the script that puts `./.sources/<repo>` at it.
- `scada.Dockerfile`, `scada.Dockerfile.dockerignore`: the scada's image,
  built with a `gridworks-scada` checkout as its context.
- `build-scada-arm64.sh`: the same image for linux/arm64. Needs the
  qemu-aarch64 binfmt; never run to completion here.
- `houses.sh`, `twin_houses.py`: write `beech1/`, `beech2/` and `flo/`
  from the pinned tlayouts and registry, with the Python run in the
  scada's environment at its pin. `./houses.sh --check` fails when the
  committed folders differ from a fresh write.
- `beech1/`, `beech2/`: each house's `hardware-layout.json` (a
  `gw.house0.layout`), `operational-params.json` (a
  `gw.operational.params`) and `ta-deed.json`, a simulated asset attested
  so the scada accepts dispatch.
- `plant-overrides.json`: both plants' `--fmu-overrides`. Written by
  hand. It has the outdoor temperature and `PZoneValve` (175 W).
- `mosquitto-1884.conf`: beech2's scada's local broker, port 1884.
