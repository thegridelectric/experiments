# runbook — correct-house0 windows, 2026-09-18

Every command below ran from `experiments/` on the laptop, with the local
`gw-dev-rabbit` container up. Times in the README timeline are ET on the
laptop clock; the box clocks run about 70 seconds behind it.

## Pre-flight

    ./beech_window.sh status
    ./spruce_window.sh status

`status` prints the house's plant services, whether a window scada is
running, whether the `ssh -R 1885` tunnel is open, and the relay bits
(spruce: gw108 at 0x21 register 3; beech: the two Krida port words at 0x20
and 0x21).

Both box checkouts were already at the laptop's pushed scada head
(`jm/spruce-unlimbo` `cd34f5ef`) and at `experiments` `5c30b84`; `on`
refuses otherwise, and also refuses unless the box's window layout pair is
byte-identical to `tlayouts/output/<house>/`.

## The windows

    ./beech_window.sh on 30
    ./spruce_window.sh on 30

Watch either one from the laptop:

    ../gridworks-scada/gw_spaceheat/venv/bin/gwa watch spruce
    ../gridworks-scada/gw_spaceheat/venv/bin/gwa watch beech

Close a window (also copies the window log to `../scratch/` and restarts
the services that were stopped at `on`):

    ./spruce_window.sh off
    ./beech_window.sh off

## The broker-side capture that did not work

    mosquitto_sub -h localhost -p 1885 -t '#' -v

This failed with `Connection error: Connection Refused: bad user name or
password` — the scada user in the laptop `.env` is not a valid user on the
dev rabbit. No broker-side capture of this run exists. Credentials stay in
the `.env`; nothing here quotes them.

## Evidence gathered afterwards (read-only on the boxes)

Window logs came from the `off` step into `../scratch/`. The event files
and the window layouts were copied off the boxes with `scp`:

    scp 'spruce:~/.local/share/gridworks/scada-experiment/event/2026-09-18T00:00:00+00:00/*.json' .
    scp 'beech:~/.local/share/gridworks/scada-experiment/event/2026-09-18T00:00:00+00:00/*.json' .
    scp 'beech:~/.config/gridworks/scada-experiment/hardware-layout.json' beech-window-layout.json
    scp 'beech:~/.config/gridworks/scada/hardware-layout.json' beech-deployed-layout.json
    scp 'spruce:~/.config/gridworks/scada-experiment/hardware-layout.json' spruce-layout.json

The spruce winter hack's own restore lines came from the box journal:

    ssh spruce 'sudo journalctl -u spruce-winter-hack --since "19:15" --no-pager'

## Instances

    uv run python emit_instances.py

Writes `instances/<house>-gw.experiment.run-000.json` from the first and
last stamped line of each window log, constructing through the gwexp
snapshot class and reading the written file back through the codec.
