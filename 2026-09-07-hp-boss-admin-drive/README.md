# hp-boss admin drive, local sim (2026-09-07)

Status: Verified · Pass 0 · Updated 2026-09-07 · Reviewed 2026-09-07@30fbac27+

> What this is: rung 2 of the hp-boss chunk's witness. The real admin
> client, over the dev broker, turns the heat pump off and on through
> hp-boss on a locally running scada (Nolan layout, SimGw108 board).
> Rung 1 is `tests/actors/test_hp_boss.py`; rung 3 is the same drive on
> honeysuckle with pin readback.

## Result: PASS

`admin-drive.log` (admin side) and `scada-excerpt.log` (scada side).
Admin link active → TurnOff dispatched to `admin.hp-boss` → scada wakes
into Admin, LocalControl Dormant → hp-boss sends OpenRelay to
`admin.hp-boss.hp-scada-ops-relay` → TurnOn → CloseRelay the same way →
release → LocalControl wakes to Normal. Scada at `30fbac27` plus the
uncommitted gate removal (the first run at `30fbac27` alone had hp-boss
ignore every command with "actuators not ready").

## Reproduce

Dev broker `gw-dev-rabbit` up (MQTT 1885). From `gridworks-scada`, with
its `.env` pointing at `tests/config/gw.nolan.layout.json`:

```sh
export PYTHONPATH=$PWD/gw_spaceheat
SCADA_ADMIN__ENABLED=true SCADA_ADMIN__HOST=localhost SCADA_ADMIN__PORT=1885 \
SCADA_ADMIN__USERNAME=smqPublic SCADA_ADMIN__PASSWORD=smqPublic \
  gw_spaceheat/venv/bin/gws run > scada.log 2>&1 &
sleep 25
gw_spaceheat/venv/bin/python <this dir>/hp_boss_admin_drive.py admin-drive.log
grep -i 'hp-boss\]\|Message from Admin\|releases' scada.log
```

The driver uses the admin package's own `AdminClient`, so the wire shape
is the TUI's.
