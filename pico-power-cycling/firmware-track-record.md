# Pico firmware track record

> What this is: the dated history of which gridworks-pico build the
> starter-scripts API served to which pico, read from each box's
> `~/starter-scripts/code_uploaded/` folder (one file per upload,
> `new_code_<pico>-uploaded-<epoch>.py`). The served file has no
> version or commit string, so its md5 is matched to the commit whose
> inline-net file has the same bytes. Evidence: a box listing taken
> 2026-10-14 (`2026-10-14-reboot-storm/box-census/`); extend this file
> at every reflash rather than re-listing.

## Builds seen in 2026

| md5 (first 8) | file | gridworks-pico commit | note |
|---|---|---|---|
| e9ab9a28 | `tank_module/tank_module_3_main_no_net.py` | `90af6de` = main `6a713e1` (2026-09-22) | adds the params retry: a pico whose boot-time params post failed retries every 30 s and calls `machine.reset()` when the scada answers late |
| 6db14a82 | `btu_meter/async_btu_main_no_net.py` | `90af6de` = main `6a713e1` (2026-09-22) | same change for the BTU meter |
| cd8483c2 | `tank_module/tank_module_3_main_no_net.py` | `0ca8a2f` (2026-09-15) | the inline-net overhaul: `net.py` folded into the main, backup-URL mechanism removed, reconnect-on-failed-post, `tank.module.params` 200 |
| bf8a7a9d | `btu_meter/async_btu_main_no_net.py` | `0ca8a2f` (2026-09-15) | same overhaul for the BTU meter |
| beaf60cf | tank main | not on `main` (a `jm/pico-overhaul` build) | spruce only, 2026-09-09 |
| 1d6fcd48, 0db18f01 | tank main | not on `main` | spruce, 2026-02-14 |

Before 2026 the Wiznet houses ran the 2024-12-28 push (tank `ee2d49ea`
/ `692bd33d`, `tank.module.params` 110) for twenty-one months.

## Rollout, 2026 (ET)

| when | box | build | picos |
|---|---|---|---|
| 02-14 08:33 | spruce | tank 1d6fcd48, 0db18f01 | 586e36, 672531 |
| 09-09 06:41, 12:16 | spruce | tank beaf60cf | 206032, 9a7935, 239531, 672531 |
| 09-15 16:19 | spruce | tank cd8483c2; btu bf8a7a9d | 672531; 108a2b, 387631, 3a7732, 661635 |
| 09-22 11:17 | beech | btu bf8a7a9d | 7a4d2b |
| 09-29 17:21 | oak | tank cd8483c2 | 31ac21 (tank2) |
| 09-30 10:42 | maple | tank cd8483c2; btu bf8a7a9d | 219430, 219530, 8a2a21, 8f5530; 0d5b31, 18a132 |
| 10-01 15:09 | beech | tank e9ab9a28; btu 6db14a82 | 319230, 72a121, 742221, 81a436; 7a4d2b |
| 10-01 15:41 | fir | tank cd8483c2 | 489530, 4eaa21, 8e5e21, 8f282a |
| 10-01 16:07 | oak | tank cd8483c2 | 16a321, 31ac21, 62ab21, 64ac21 |
| 10-02 10:02–10:11 | beech, fir, maple, oak, spruce | tank e9ab9a28; btu 6db14a82 | every tank pico above; btu 7a4d2b, 0d5b31, 18a132, 3a7732, 661635; spruce tanks 206032, 239531, 27432a |
| 10-02 16:01 | spruce | btu 6db14a82 | 108a2b |

Where that leaves the fleet: every tank pico seen in 2026 runs
e9ab9a28 except spruce's 672531 (cd8483c2, 09-15) and 9a7935 (beaf60cf,
09-09); spruce's btu 387631 still runs bf8a7a9d. elm has received
nothing in 2026 (both boxes unreachable over tailscale on 10-02 and
10-14). The `*2` boxes hold no 2025–26 uploads and their
starter-scripts checkouts are one to two years old.

## Reading the boxes

The listing behind this file, run read-only over ssh on 2026-10-14:

    ls -la --time-style=full-iso ~/starter-scripts/code_uploaded/
    md5sum ~/starter-scripts/code_uploaded/*.py
    git -C ~/starter-scripts log -8 --format='%h %ci %s'

and the md5 ↔ commit match on the laptop:

    cd gridworks-pico && for c in 6a713e1 90af6de 0ca8a2f; do \
      git show $c:tank_module/tank_module_3_main_no_net.py | md5 -q; done
