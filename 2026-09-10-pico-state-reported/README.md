# pico-state-reported, 2026-09-10

> What this is: the pico-cycler's per-pico `single.pico.state` rows
> reaching the journal as `<node>-pico-state` channel readings, first
> on the dev broker (a PASS, one afternoon on the laptop) and then from
> spruce in the production journal, with the command that reads them.

## Read the latest pico states (start here)

`read_pico_states.py` pulls the newest N `single.pico.state` rows for
spruce from the production journal and decodes them with the
journalkeeper's own enum. The journal stores a state as the value's
index in the enum word's value list (`report_event_persistor.py`
`get_sema_enum_value`), so `SinglePicoState.values()[value]` is the
name. Run it from the journalkeeper repo as a sibling, whose env has the
vendored enum; `GJK_DB_URL` comes from `experiments/.env`:

```sh
cd gridworks-journalkeeper
set -a; . ../experiments/.env; set +a    # exports GJK_DB_URL (the script also reads that file itself)
uv run python ../experiments/2026-09-10-pico-state-reported/read_pico_states.py 20
```

The 20 newest rows at 18:22 UTC on 2026-09-10, oldest first (two
periodic rosters, every pico Alive):

```
18:09:58  dist-btu-pico-state          0  Alive
18:09:58  buffer-pico-state            0  Alive
18:14:58  tank1-pico-state             0  Alive
18:14:58  store-btu-pico-state         0  Alive
18:14:58  secondary-btu-pico-state     0  Alive
18:14:58  primary-btu-pico-state       0  Alive
18:14:58  pipes1-pico-state            0  Alive
18:14:58  floor1-pico-state            0  Alive
18:14:58  fancoil-pico-state           0  Alive
18:14:58  dist-btu-pico-state          0  Alive
18:14:58  buffer-pico-state            0  Alive
18:19:58  tank1-pico-state             0  Alive
18:19:58  store-btu-pico-state         0  Alive
18:19:58  secondary-btu-pico-state     0  Alive
18:19:58  primary-btu-pico-state       0  Alive
18:19:58  pipes1-pico-state            0  Alive
18:19:58  floor1-pico-state            0  Alive
18:19:58  fancoil-pico-state           0  Alive
18:19:58  dist-btu-pico-state          0  Alive
18:19:58  buffer-pico-state            0  Alive
```

## Dev rung, before the pull (laptop, dev broker)

Journalkeeper `3a8bc57` on a fresh local database, the actual-spruce
scada `69d5d6ec` on the sim Nolan layout (`tests/config/nolan-layout.json`,
`SCADA_IS_SIMULATED=true`) with an LTN peer from the same checkout,
because the scada sends `layout.lite` on link activation and uploads
its `report.event`s only over an active link.

**PASS.** From the scada's `layout.lite` 012 the journalkeeper created
`buffer-pico-state` and `tank1-pico-state` (unit type
`single.pico.state`); the readings read back Alive then Flatlined in
time order. What it settled for the plan:

- **The cycler's own state is not a channel.** The journalkeeper
  creates no `pico-cycler` state channel, so roster rows cannot be
  ordered against the cycler's cycle in the journal; in the scada log
  the cycle (`PicosLive → RelayOpening` on `PicoMissing`) comes first
  and the Flatlined rows follow at the cycler's 60 s wait.
- **The journalkeeper's log does not say when it drops a reading.**
  A reading with no channel to land in is dropped and counted, but the
  live process never prints that count (only the S3 importer does), so
  "nothing dropped" cannot be read off the log. The evidence that the
  roster rows were not dropped is the channels existing and the rows
  being in them.
- **`jm/spruce-unlimbo` emits `layout.lite` 013**, staging and outside
  the journal seed (published set ending at 012); a journal rung for
  that line waits on promotion, not on code. actual-spruce emits 012.
- Sim picos on actual-spruce never post (that line has no sim pico
  loop), so a recovery to Alive is not producible on the laptop; the
  production rows below have it.

## Pico states from the production journal (spruce)

Spruce is the only house that reports `single.pico.state` (scada
`69d5d6ec` on `actual-spruce`, journalkeeper `4f0a932` on `main`, both
deployed 2026-09-10). With `GJK_DB_URL` from `experiments/.env`:

```sh
set -a; . experiments/.env; set +a
psql "$GJK_DB_URL" -At -F' ' -c "
  select to_char(r.timestamp at time zone 'UTC','HH24:MI:SS') utc, c.name, r.value
  from gridworks.readings r
  join gridworks.reading_channels c on c.id = r.channel_id
  where c.terminal_asset_alias = 'hw1.isone.me.versant.keene.spruce.ta'
    and c.unit_type = 'single.pico.state'
    and r.timestamp > now() - interval '8 hours'
  order by r.timestamp, c.name"
```

Values: 0 Alive, 1 Flatlined, 2 Zombie. Keep the time bound; an
unbounded join on `readings` hits the statement timeout. The full
result of the run at 18:15 UTC is `spruce-pico-states.txt` (281 rows
from the 15:59 UTC restart); the state changes in it:

| UTC | Pico | State | What it was |
| --- | --- | --- | --- |
| 15:59:49 | all nine | 0 | start-up roster after the restart |
| 16:00:59 | buffer, tank1, fancoil, floor1, pipes1 | 1 | the five tank modules flatline together |
| 16:03:09–16:04:14 | the same five | 2 | zombie after the cycler's reboot cycles fail |
| 16:14–17:13 | secondary-btu | 1 → 0, 1 → 2 → 0, 1 → 2 | the one BTU that keeps dropping out |
| 17:37:17 | the five + secondary-btu | 0 | the pi gets 192.168.2.200 back (the address the tank modules post to; lost in the router replacement) |
| 17:38:27 → 17:38:47 | the five | 1 → 0 | one more flatline and recovery as the boards settle |
| 17:50:17 → 17:51:41 | secondary-btu | 1 → 0 | |

The roster told the story on its own: five picos of one kind dark
together while the other kind stayed alive, from a fixed moment, is a
path failure, not five boards.

## Folder contents

- `README.md` — this record.
- `read_pico_states.py` — the decoding reader above.
- `spruce-pico-states.txt` — the production-journal rows above, from
  the command above.

The dev rung's captures, harness and decoded instances were laptop
artifacts of one afternoon and are not kept; the findings are above.
