# dev-sim

What this is: the dev simulation as one Pod for `podman kube play`. Two
simulated Beech houses (a scada, a plant and an LTN each) run with the
FLO, the price service, the market maker, the weather service, the
journal and the web app, all in universe `d1`, run `d1__1`. It is a
standing stack and has no date. The record of its first runs is
`../2026-11-11-beech-sim-compose/`.

## Run

    ./run.sh
    ./stop.sh

`run.sh` builds the images and plays `pod.yaml`. It needs Podman, the
sibling checkouts `build.sh` names (`gridworks-terminalasset`,
`gridworks-scada`, `gridworks-flo`, `optimal-flexibility`,
`gridworks-price-forecast`, `gridworks-marketmaker`,
`gridworks-journalkeeper`, `gridworks-web-backend`,
`gridworks-web-frontend`), the ISO-NE account in `./price.env` and
`./mm.env` (gitignored; `pod.yaml`'s header gives the names), and the
bruce volume filled once per house shape (the command is in `pod.yaml`'s
header). Each image is built from whatever its checkout is on.

Three ports are published on the host: the web app on 5173
(`http://localhost:5173/gridworks-web-frontend/`, login `beech` /
`beech`), the realtime gateway on 8100, and the journal database on
5433. Everything else is on the pod's localhost.

`stop.sh` drops the journal database with the pod. `./eventstore`,
`./events`, `./events-buffer` and the bruce volume stay.

## The houses

`house/` is `d1.isone.me.versant.keene.beech.at` at `AllTanks` and
`house-buffer/` is `d1.isone.me.versant.keene.beech.buf` at
`BufferOnly`, the same plant, so the two can be compared. Both LTNs bid
into the one market maker, `d1.isone.me.versant.keene`, so the two
houses share a market.

`gen_layout.sh` makes them with tlayouts' House0 generator at `4572c35`.
Their params name `flo.tuning.bruce` 002, so the scada image is built
from a `gridworks-scada` whose snapshot has that version (`main` at
`45cd599d` does), and the FLO image from a `gridworks-flo` that decodes
it.

## Files

- `run.sh`: builds the images (cached layers; a later run rebuilds an
  image only when its files changed) and starts the pod.
- `build.sh`: the image builds, on their own.
- `package.sh`: zips the images this tree builds and the files another
  box needs to run the sim, without the sibling checkouts.
  `./package.sh --dry-run` lists them. The zip's `run.sh` loads those
  images, pulls Rabbit, Mosquitto, Postgres and Timescale, and plays
  the pod. It holds `price.env` and `mm.env`.
- `stop.sh`: stops the pod. The journal database goes with it.
  `./eventstore`, `./events`, `./events-buffer` and the bruce volume stay.
- `pod.yaml`: the stack as one Pod, for
  `podman kube play`: two scada+ta pairs (AllTanks beech-at and
  BufferOnly beech-buf) and an LTN for each, the FLO they ask, the price
  service the LTNs read (`gwpf rabbit` and `gwpf api`, one image), the
  market maker they clear against (`gwmm rabbit`), the weather service
  they read (`gwwf rabbit` and `gwwf api`, its own Postgres on
  pod port 5436, dev records minted at each start), and the journal: the
  ear writing `./eventstore` (`ear listen --no-s3`), TimescaleDB
  published on host port 5433, the keeper, and the web app on host
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
  its context. `journal_boot.py` creates the dev roles and the
  `gridworks` tables before the keeper starts.
- `weather.Dockerfile`, `weather.Dockerfile.dockerignore`: the weather
  service's image, built from
  `https://github.com/thegridelectric/gridworks-weather-forecast.git`.
  The scada and the LTN read `http://127.0.0.1:8531/d1-weather`.
- `ear.Dockerfile`, `ear.Dockerfile.dockerignore`: the ear's image,
  built from `https://github.com/thegridelectric/gridworks-ear.git`.
  With `--no-s3` it writes each message under `./eventstore`.
- `web.Dockerfile`, `web.Dockerfile.dockerignore`: the web backend's
  image, built with a `gridworks-web-backend` checkout as its context.
  `python -m api` reads the journal; `python -m gateway` serves the
  realtime page.
- `frontend.Dockerfile`, `frontend.Dockerfile.dockerignore`: the web
  frontend's image, built with a `gridworks-web-frontend` checkout as
  its context. Vite proxies `/api` to the API in the pod. At start the
  container reads each house's GNode alias and `WeatherBundleName` from
  `./house` and `./house-buffer` into `VITE_HOUSE_WEATHER_BUNDLES`, so
  the weather panel draws the bundle that house's operational params
  name.
- `flo.Dockerfile`, `flo.Dockerfile.dockerignore`: the FLO's image, built
  with a `gridworks-flo` checkout as its context and the sibling
  `optimal-flexibility` as the `bruce` context.
- `flo_matrix.py`: fills the bruce volume with the house's transition
  matrices, one per seasonal storage mode, run once in the FLO's image.
  Beech's took 535 s (AllTanks) and 1105 s (BufferOnly) on one core,
  peaking at 452 MB.
- `flo/g.node.gt.json`: the FLO's identity, `d1.flo` under the dev
  universe's GNodeId. Written by the generator.
- `scada.Dockerfile`, `scada.Dockerfile.dockerignore`: the scada's image,
  built with a `gridworks-scada` checkout as its context.
- `build-scada-arm64.sh`: the same image for linux/arm64. Needs the
  qemu-aarch64 binfmt; never run to completion here.
- `gen_layout.sh`, `beech_sim_gen.py`: the houses' generator. The shell
  script extracts tlayouts at the pinned commit and runs the Python in the
  scada's environment, once per house.
- `house/hardware-layout.json`, `house/operational-params.json`: the
  AllTanks generator output, a `gw.house0.layout` and a
  `gw.house0.operational.params`. Regenerating gives the same params
  and a layout that differs only in its component and ShNode ids.
- `house/ta-deed.json`: the AllTanks house's `ta.deed`, a simulated
  asset attested so the scada accepts dispatch. Written by the generator.
- `house/plant-overrides.json`: the plant's `--fmu-overrides`. Written by
  hand. Holds the outdoor temperature and `PZoneValve` (175 W).
- `house-buffer/`: the BufferOnly pair, `d1.isone.me.versant.keene.beech.buf`,
  the same plant overrides. Written by the generator.
- `mosquitto-1884.conf`: the BufferOnly scada's local broker, port 1884.
