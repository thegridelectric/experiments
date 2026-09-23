# Field-window recipe

A **field window** runs the unlimbo scada on a real house for a bounded
time, from the laptop, swapping the house off its deployed plant control for
the duration. It is the live counterpart to a spot-check: a spot-check reads
what a house already emitted (see `spot-check-recipe.md`); a window makes a
house run new code and watches it happen. A window mutates the box — it stops
the production plant services and boots a different scada against a different
layout — so it is run with care and always bounded.

Both are the two operational modes for working with the production machines:
this file is the live/real-life path, `spot-check-recipe.md` is the
after-the-fact data-analysis path. They share the house map and the spruce
branch exception below.

## Two kinds of window

- **Experiment window** — kept short and tightly bounded. The point is to
  observe the branch under close-to-real conditions and get out. At spruce in
  the heating season the winter hack (`NolanLocalControl`) is the plant
  controller holding zones off and the heat pump off, so an experiment window
  there displaces real control: keep it brief.
- **Field-support window** — deliberately long (hours). Here the window scada
  is the thing that lets heat calls reach the heat pump while someone works on
  the equipment, and a cold house is the reason for the work. Bound it anyway
  (e.g. `on 360` for six hours) so the winter hack auto-restores if the
  session ends, and extend with a fresh `off`/`on` as the work runs on.

## Houses

`house_window.sh` targets `dev`, `spruce` and `beech` (a house target is the
ssh host of the same name); `put_layout.sh` also handles `maple`. The rest are
layouts arriving this fall, not yet windowed.

| House | Window layout family | Beta window up |
|---|---|---|
| spruce | `gw.nolan.layout` | yes |
| beech | `gw.house0.layout` | yes |
| maple | `gw.house0.layout` | no |
| fir / oak | `gw.house0.no.sieg.layout` | no |
| elm | `gw.house0.monoblock.layout` | no |

LTN dispatch of a windowed house requires all of: the LTN `.env` sets
`monitor_only=False`; the scada's ops word has `ActuationAuthority Active` and
`ServiceMode Heating`; and the scada holds a TaDeed. A Standby house cannot be
dispatched.

## The spruce branch exception

The fleet default is that a box runs production off `main`. **Spruce is the
exception, in both repos**, confirmed on the box:

- `~/gridworks-scada` → **`actual-spruce`** — the production plant control
  (`gwspaceheat`, and in the heating season the `spruce-winter-hack` service).
- production layout ← tlayouts **`actual-spruce`** (`gen_spruce.py` /
  `spruce.json`, deployed as `hardware-layout.json`).
- `~/gridworks-scada-unlimbo` → **`jm/spruce-unlimbo`** — the window scada.
- window layout ← tlayouts **`jm/spruce`** (`spruce_gen.py`, the
  `output/spruce/` Nolan pair).

So spruce carries two scada checkouts and two layouts that must be reasoned
about separately. Beech's window runs the same `jm/spruce-unlimbo` scada; its
production branch is the fleet default.

## The two box layouts

A house that has a window keeps two layouts on the box, one per scada:

| Layout | Path on box | Read by | Source of truth |
|---|---|---|---|
| production | `~/.config/gridworks/scada/hardware-layout.json` | production scada (winter hack) | tlayouts `actual-spruce` |
| window | `~/.config/gridworks/scada-experiment/hardware-layout.json` + `operational-params.json` | window scada | tlayouts `jm/spruce` `output/spruce/` |

When a hardware fact changes (a pico swap, a channel), **both layouts need the
change** — they answer to different branches. Confirm the pico id and the
derived channels in each.

The window pair reaches the box only through `put_layout.sh`, never scp or a
hand-edit:

- `./put_layout.sh <house> check` — compare the box's window files to
  `../tlayouts/output/<house>/` by sha256; exit non-zero if either differs.
  This is the read-only gate; `<house>_window.sh on` refuses until it passes.
- `./put_layout.sh <house> <change>` — for each file that differs, leave a
  dated `*.<date>-pre-<change>.json` copy on the box, copy the gen output over
  it, and verify the sha256. Run the house's gen first
  (`../tlayouts/<house>_gen.py` from the scada venv); this script copies bytes
  and does not regenerate. `<change>` is a short dashed slug (e.g. `pi-ids`).

The production `hardware-layout.json` follows the ordinary scada deploy
(land-in-git → push → pull on the box), not `put_layout.sh`.

## A round

1. **Bring up.** `./<house>_window.sh status` (plant services, window, tunnel,
   relay bits). Push the scada head and pull it on the box; if a gen changed,
   regenerate the window pair and place it with `./put_layout.sh <house>
   <change>`. Then:

        ./<house>_window.sh on <minutes> [--debug] [--ltn]
        ../gridworks-scada/gw_spaceheat/venv/bin/gwa watch <house>

   `on` refuses unless the box's window pair is byte-identical to the laptop's
   gen output, the laptop's scada head is pushed and the box checkout is at it,
   and no window scada is already running. It starts `capture_broker.py` on the
   laptop's dev broker if none is running, opens the `ssh -R 1885` tunnel
   (upstream observation only; commands ride the box's own mosquitto on 1883),
   records the running plant services, stops them, and boots the window scada
   from `~/envs/dev.env`. No minutes = a standing window until `off`.
   `--debug` sets scada loggers to DEBUG; `--ltn` runs the LTN on the laptop
   against the target's layout; `dev` rehearses on the laptop's own sim pair.

2. **Collect.** The broker capture records everything published to the dev
   broker. Snapshots, power, forecasts and the layout/deed announcement publish
   with no LTN; `report.event`s do not — they ride the acked path and, with no
   LTN peer, persist on the box. Pull them after the window, read-only:

        scp -r <house>:/home/pi/.local/share/gridworks/scada-experiment/event/ ../scratch/<house>-events/

   Or open with `--ltn` to get the reports live on the capture.

3. **Close.** `./<house>_window.sh off` if the bound has not already closed it,
   then `status` to confirm the recorded plant services are running again. The
   box restarts exactly the services it stopped when the window scada exits for
   any reason (bound, crash, or `off`), and `off` copies the log to
   `../scratch/`. Stop the shared capture after the last window:
   `./house_window.sh capture off`.

Window logs and the broker capture arrive in `../scratch/`; window layouts on
the box pull read-only from
`<house>:~/.config/gridworks/scada-experiment/`.

## Records: only the last run is kept

Unlike an ordinary experiment, the field-window practice does not archive
every round. It keeps only the **most recent** run — its window log(s), any
bus/port capture, and the `gw.experiment.run` instance that `emit_instances.py`
builds from the log's first and last stamped lines. **Opening a new window
deletes the previous run's artifacts first**; git history and the logbook line
carry what a past round taught, so nothing durable is lost. `emit_instances.py`
is the only code that persists between runs.

## On Tap (for Jessica)

- **Set up a local LTN as part of the beta field test** — this way we get all
  the `report.event`s.
- **Test that an incorrect ActuationAuthority results in no DispatchContract.**
