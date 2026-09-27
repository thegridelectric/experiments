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

`house_window.sh` and `put_layout.sh` target `spruce`, `beech` and `maple`
(a house target is the ssh host of the same name); `house_window.sh` also
takes `dev`. The rest are layouts arriving this fall, not yet windowed.

The expected posture of each house's window pair, read from the gen's
ops params before `on` and checked against the `layout.lite` the window
announces. Beech is Standby on purpose: its window runs the House0 code
on a production house without letting a dispatch reach the equipment.

| House | Window layout family | ServiceMode | ActuationAuthority | Beta window up |
|---|---|---|---|---|
| spruce | `gw.nolan.layout` | Heating | Active | yes |
| beech | `gw.house0.layout` | Heating | Standby | yes |
| maple | `gw.house0.layout` | Heating | — | no |
| fir / oak | `gw.house0.no.sieg.layout` | Heating | — | no |
| elm | `gw.house0.monoblock.layout` | Heating | — | no |

**Every house but spruce has a second pi** (`maple2`, `beech2`) running
`gwspaceheat2` from its own `~/gridworks-scada` checkout and
`~/.config/gridworks/scada2/`. It captures the analog-temp channels
(`hp-lwt`, `hp-ewt`, the pipe temperatures) and posts them to a mosquitto
the scada also uses, where the scada takes them under its own layout's
encoding: a reading carries no unit on the wire, so **both pis must hold
the same layout**. The window therefore reaches the second pi with the
same kit as the first: `~/gridworks-scada-unlimbo` (the branch refuses the
non-sema production layout, and `main` cannot load the sema one),
`~/envs/dev.env`, and the window pair in
`~/.config/gridworks/scada-experiment/`, placed and byte-checked by
`put_layout.sh <house>` on both boxes. `<house>_window.sh on` stops
`gwspaceheat2` and its restart timer, boots the branch scada2
(`window_boot.py` with `WINDOW_SCADA2=1`) on the window pair, and `off`
restores them; nothing production reads is rewritten. The two pis boot at
once, `on` ends the window on both unless both come up, and a watcher on
the laptop ends it on both when it ends on either, so a bound or a crash
never leaves one pi on the branch beside the other on production. A laptop
asleep or off the network leaves each pi to its own bound.

The shared mosquitto differs by house. At maple it is on the first pi, for
production and window alike. At beech production uses the one on `beech2`
(the deployed `.env` on beech names `beech2.local`), while the window scada
listens on beech's own, so beech2's window env points its local link at
`beech.local`.

LTN dispatch of a windowed house requires all of: the LTN `.env` sets
`monitor_only=False`; the scada's ops word has `ActuationAuthority Active` and
`ServiceMode Heating`; and the scada holds a TaDeed. A Standby house cannot be
dispatched.

## Picos on the 110 firmware

Until the fleet's picos are reflashed (several weeks from 2026-09-24;
spruce is already done) every tank-module pico except spruce's posts
`tank.module.params` 110, and the window scada accepts only 200. A 110
pico posts its params once per boot, so expect one refusal per tank pico
at the window's startup reboot, and one more per pico cycler reboot after
that; the temperature readings still arrive. The refusal is not a finding
of the round; a run of cycler reboots is.

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
   relay bits) and `./house_window.sh capture status`: a capture left
   running from an earlier round is reused by `on`, so stop it first for a
   clean file. Push the scada head and pull it on the box:

        ssh <house> 'git -C ~/gridworks-scada-unlimbo pull --ff-only'

   If a gen changed, regenerate the window pair and place it with
   `./put_layout.sh <house> <change>` (each placement leaves a dated pre-copy
   in the box's `scada-experiment/`; prune old ones by hand). Read
   `ActuationAuthority` and `ServiceMode` from the gen's ops params and
   check them against the Houses table. Then:

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

   Watch the window scada live from the laptop (the box writes it to
   `/tmp/<house>-window/boot.log`; `off` copies it to `../scratch/`):

        ssh <house> tail -f /tmp/<house>-window/boot.log

2. **Collect.** The broker capture records everything published to the dev
   broker. Snapshots, power, forecasts, glitches and the layout/deed
   announcement publish with no LTN. Events, `report.event` included, ride
   the acked path: with no LTN peer the upstream link never goes active and
   they persist on the box. `off` pulls the ones stamped since the window's
   start into `../scratch/<house>-events-<stamp>/` and prints the
   `report.event` count; open with `--ltn` to get them live on the capture
   instead. Every round reads the reports as well as the snapshots: which
   channels each slot carries and at what cadence (a first reading at boot,
   one per change, one per 300 s boundary). A bounded window is at least
   11 minutes so it saves the first full-slot report; `on` refuses shorter.

   A channel with no value whose capturing node is a pico is confirmed
   missing after the window, with the scada stopped, by dropping the 5V
   bus and watching the bank re-post into the starter-scripts API: the
   method and the scripts (`turn_off_5v.py` / `turn_on_5v.py`, keyed on the
   pi's hostname, and `start_api.sh`) live in `starter-scripts/` on the box.

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
