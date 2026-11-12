# beech-sim-compose, 2026-11-11

> What this is: a simulated Beech as one `docker compose` stack: a whole
> scada and the Beech plant it runs (`ta-plant` on `BeechPlant.fmu`), with
> the two brokers they meet on (OPS-40). Does the scada run the plant's
> physics through its relays, and does it see the result in its channels?
> Verdict: PASS over 13 and a half hours, an on-peak evening and the
> off-peak night after it. The scada held the heat pump off on peak,
> called it off peak, filled the buffer and charged the store.

## Why

The plant loop (`../2026-11-10-plant-loop/`) put a scada behind the plant
link with a plant whose values drift at random: its relays reached the
plant and moved nothing. A plant with physics closes the loop the other
way: a relay the scada moves changes what the scada then reads. Beech is
the first House0 house with a model (`gridworks-terminalasset`,
`modelica/Beech.mo`), and a stack that starts with one command is what a
fleet of simulated houses is made of.

## Setup

Laptop, four containers in one compose project, `beech-sim`
(`compose.yaml`):

- **`rabbit`**: `ghcr.io/thegridelectric/dev-rabbit:latest`, the dev
  broker, vhost `d1__1`.
- **`mosquitto`**: `eclipse-mosquitto:2`, anonymous on 1883, the scada's
  local MQTT.
- **`plant`**: the `gridworks-terminalasset` image, `ta-plant --layout
  /house/hardware-layout.json --fmu /opt/gwta/BeechPlant.fmu`, five-second
  flux, as `d1.isone.me.versant.keene.beech.ta`. Built from
  `gridworks-terminalasset` branch `ow/beech-plant`, the content of
  `f90dcd2`.
- **`scada`**: `gws run --message-summary --seconds-per-report 60` from
  `gridworks-scada` branch `ow/plant-seam`, which holds the plant link,
  the content of `8755ba34`, in the image `scada.Dockerfile` builds from
  that checkout.
  `SCADA_WEATHER_SOURCE=Sim`, plant link `Broker` (the default), no deed,
  no LTN: the upstream link never activates and reports are persisted,
  not published.

The four share the broker's network namespace, so each finds the others
on localhost at the ports it uses on a laptop (AMQP 5672, MQTT 1885,
local MQTT 1883) and the compose file holds no address and no credential.
Nothing is published to the host: the stack ran beside the laptop's
standing `gw-dev-rabbit` and a dev scada on it, and touched neither.

**The house** (`house/`, read-only in both containers): a `gw.house0.layout`
and its `gw.house0.operational.params`, made by `gen_layout.sh` with
tlayouts' House0 generator at `10110cc`. It is the all-sim House0 that
tlayouts authors for orange, with what makes it Beech changed: two zones
(`down`, `up`), three 120-gallon store tanks, rolling distribution
energy, and GNodes of its own under `d1.isone.me.versant.keene.beech`.
What it keeps from orange and the real Beech does not have: the
operational params (no operator hold, so local control runs the house;
seasonal storage `AllTanks`) and the Siegenthaler strategy `StratProtect`
(the real Beech holds full send). The scada copies the pair into its
config home under their deployed names at each start.

**The plant's coefficients** are the Modelica model's placeholders.
`house/plant-overrides.json` is the place to change them: any parameter
of `Beech.Plant`, and the outdoor temperature, which the plant holds at
-5 °C.

## Found

PASS (`logs/check.json`), 2026-11-11 21:49:57 to 2026-11-12 11:23:35 UTC:

- **The scada's relays reach the plant.** The plant heard 2593 actuations
  across all 15 relays of the layout.
- **The plant's channels reach the scada.** All 50 plant-fed channels are
  in the scada's 813 minutely reports, and all 50 moved.
- **The loop is closed, on peak and off.** The run began on peak (16:00
  to 20:00 ET): local control (`AllTanks`) held the heat pump off and ran
  the store pump to discharge a store that began no warmer than the
  buffer, the thermostats called from the start, the distribution pump
  moved 5.2 gpm, and the buffer fell from 30 °C to 26 °C at the top. One
  minute into off-peak it called the heat pump, which drew up to 4.5 kW
  across its two units at up to 6.4 gpm. The buffer top reached 51.7 °C.
  From 04:49 UTC local control charged the store in five periods
  (`HpOnStoreCharge`), each ended by the buffer emptying: tank 1's top
  reached 44.8 °C and tank 3's bottom 38.2 °C. The zones fell to 17.0 °C
  on peak and recovered to 20.3 °C.
- **The scada's primary pump relay never closed.** Local control left the
  primary pump to the heat pump (`SwitchToHeatPump to
  primary-pump-failsafe-relay`), and the plant's heat pump ran it.
- **A scada can be replaced under a running plant.** The scada's
  container was rebuilt and recreated 17 minutes after the other three;
  the plant kept its state and heard the new scada's relays.

Two things the run showed about the scada, neither changed here:

- **The Siegenthaler loop goes blind with the heat pump running.** At
  01:01:31 UTC, 23 seconds after local control turned the heat pump on,
  the loop logged `Blind: 3780W over 500W 120s after off; hp-boss last
  turned to HpOff 11490s ago`, then `BecameBlind: HpStartingUp -> Blind`,
  drove the valve to full send and stayed blind for the rest of the run.
  hp-boss said `HpOn` at that moment (the `Engaging brain` line before
  it). `StratProtect.blind_reason` counts from `hp_turned_off_time`,
  which is set when the heat pump turns off and not cleared when it turns
  on, so any run drawing over 500 W more than 120 seconds after the last
  off reads as blind (`gw_spaceheat/actors/sieg_loop/strat_protect.py`).
- **Three `report.event`s fail the scada's own sema snapshot.** The
  Siegenthaler loop's valve-state `fsm.atomic.report`s carry `ReportType:
  Event` and no `Event`, which `fsm.atomic.report`'s Axiom 2 refuses
  (`first_refusal` in `logs/check.json`). The check decodes each
  `channel.readings` on its own for that reason.

## Timeline

2026-11-11 and 12, ET.

- 14:49 to 15:14: a first run of 25 minutes, off peak, PASS: the heat
  pump was called 73 seconds after the containers were created. Its logs
  were replaced by this run's.
- 16:32:55: the four containers created; the plant and the scada start
  once the broker is healthy.
- 16:49:57: the scada's container recreated from an image that logs why
  the Siegenthaler loop goes blind. The run is counted from here.
- 16:50:06: local control starts on peak with the buffer empty:
  `HpOffStoreDischarge`. The Siegenthaler loop moves to full keep.
- 20:00:08: off-peak starts; the store pump stops.
- 20:01:08: local control turns the heat pump on; the Siegenthaler loop
  moves to just keep.
- 20:01:31: the Siegenthaler loop goes blind and drives the valve to full
  send, there by 20:03:15. The heat pump's water goes to the buffer.
- 23:49:08 to 00:00:08, 01:30 to 01:42, 02:03 to 02:36, 03:45 to 04:23,
  05:31 to 06:09: the buffer is full and the heat pump charges the store.
- 06:23:35: the recorded check, PASS. The stack left running.

## Analysis notes

- **What the check proves and what it does not.** The verdict stands on
  the two directions of the link and on channels moving. Whether the heat
  pump runs is the scada's decision at that hour, so `the_heat_pump_ran`
  is recorded and is not a check. That a relay does to the plant what the
  house's wiring does is held by `gridworks-terminalasset`'s
  `tests/test_house0.py`, not here.
- **The weather is two weathers.** The scada's is its `Sim` source; the
  plant's outdoor air is a fixed input. No word carries one to the other.
- **Pump speeds are full.** The scada's 0-10 V levels do not cross to the
  plant, so each pump runs at full speed whatever the scada outputs.
- **The plant's valve and the scada's valve agree only by timing.** Each
  keeps its own count of the Siegenthaler motor's travel (94 s, keeping
  between 26 s and 56 s); the plant starts at the keep stop, as the scada
  assumes.
- **Expected and harmless:** one Warning glitch `no-ta-deed` at boot.
- **The images were built before the code was committed.**
  `logs/code-under-test.txt` names the commits the two checkouts were on
  and how many files each had uncommitted: those files are what
  `8755ba34` (`gridworks-scada`) and `f90dcd2`
  (`gridworks-terminalasset`) hold.

## Folder contents & experimental method

Everything here was GENERATED by this run: the scada's reports were
persisted inside its container and never published, the plant's log is
its container's stdout, and nothing is in the journal DB or the
eventstore. A re-run is a new dataset. The run touched no running
system.

The stack, from scratch (the sibling checkouts `gridworks-scada`, on a
branch with the plant link, and `gridworks-terminalasset`, on a branch
with the House0 plant, are the build contexts):

    docker compose up --build -d
    ./check.py
    docker compose down

`check.py` waits for the scada's first two minutely reports, so it can
follow `up` at once. Each run of it replaces `logs/`.

Watch it: `docker compose logs -f scada` (the message summary) and
`docker compose logs -f plant` (each relay it hears).

Temperatures, powers and flows over time, with the stack up, from every
reading the scada has persisted since it started: `logs/channels.png` has
three graphs on one time axis, every temperature, every power and every
flow; `logs/tank-temps.png` has the buffer and the store tanks, a panel
per tank and a line per depth; `logs/distribution.png` has the
distribution loop on its own (display only, gitignored with their CSV):

    uv run python plot_channels.py

The scada persists its events in its container, under
`/home/scada/.local/share/gridworks/scada/event/`, a folder per UTC day
and a JSON file per event. They go with the container; to keep them:

    docker compose cp scada:/home/scada/.local/share/gridworks/scada/event ./events

The house, from scratch (needs `10110cc` fetched in the sibling
`tlayouts` checkout):

    ./gen_layout.sh

The run's instance, from the check's evidence (from the repo root):

    uv run python 2026-11-11-beech-sim-compose/emit_instances.py

A display CSV of what the reports hold for each plant-fed channel
(readings, distinct values, low, high, last, in each channel's own
encoding), from the committed `logs/reports.json`:

    python3 -c "import csv,json,sys; d=json.load(open('logs/reports.json')); w=csv.writer(sys.stdout); w.writerow(['channel','readings','distinct_values','low','high','last']); [w.writerow([n,*d['seen'][n].values()]) for n in d['plant_fed_channels']]" > logs/reports-display.csv

- `compose.yaml`: the stack.
- `scada.Dockerfile`, `scada.Dockerfile.dockerignore`: the scada's image,
  built with a `gridworks-scada` checkout as its context.
- `gen_layout.sh`, `beech_sim_gen.py`: the house's generator. The shell
  script extracts tlayouts at the pinned commit and runs the Python in the
  scada's environment.
- `house/hardware-layout.json`, `house/operational-params.json`: the
  generator's output, a `gw.house0.layout` and a
  `gw.house0.operational.params`. Regenerating gives the same bytes.
- `house/plant-overrides.json`: the plant's `--fmu-overrides`. Written by
  hand.
- `check.py`: the verdict, run on the laptop. `stack_check.py`: what it
  runs inside the scada's container to read the persisted events.
- `plot_channels.py`: the pictures, run on the laptop.
  `channel_readings.py`: what it runs inside the scada's container to
  read the temperature, power and flow channels out of the persisted
  reports.
- `emit_instances.py`: emits the run's instance.
- `instances/beech.sim.compose-gw.experiment.run-001.json`: the run, a
  `gw.experiment.run`.
- `logs/check.json`: the verdict and what it stands on.
  `logs/reports.json`: `stack_check.py`'s output. `logs/plant.log`: the
  plant's log without its solver's start-up lines.
  `logs/scada-control.log`: the lines of the scada's log from its control
  actors. `logs/code-under-test.txt`: the two checkouts' commits and
  uncommitted file counts. `logs/scada.log`, the scada's whole log
  (200 MB), is gitignored. All written by `check.py`.
