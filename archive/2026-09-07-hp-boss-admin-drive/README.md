# hp-boss admin drive, local sim (2026-09-07)

Status: Verified · Pass 0 · Updated 2026-09-07 · Reviewed 2026-09-07@3d871690

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
release → LocalControl wakes to Normal. Scada at `8e0b95c6` (the gate removal landed) (the first run at `30fbac27` alone had hp-boss
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

## Rung 3: honeysuckle (protocol, written before the run)

**Why.** Rung 2 ran on a sim board, so the relay's confirmation was a sim
pin. Honeysuckle's gw108 reads its pin back, so the relay's
`FsmFullReport` to hp-boss is a real confirmation. The chunk's done-when.

**Setup.** Scada `3d871690` on the pi (`git pull` in `~/gridworks-scada`;
no dependency change since `ba2c9883`). The bench's standing layout has
no `hp-scada-ops-relay` and fails coverage validation at this commit, so
the run uses the dac-output pair already on the pi
(`hardware-layout.dac-output.json`, md5 prefix `67010fd5`, with
`operational-params.json` `2b9b7a50`): a Nolan layout with hp-boss and
`hp-scada-ops-relay` as a gw108 relay with pin readback, scada alias
`d1.bench.honeysuckle.scada`. Admin link on in the pi's
`gw_spaceheat/.env` per the dac-output runbook step 6 (already there).
The driver runs on the dev machine through the tunnel, since the pi's
venv has no admin package.

**Protocol.**

1. honeysuckle: `cp hardware-layout.dac-output.json hardware-layout.json`
   in `~/.config/gridworks/scada` (standing copy stays as
   `hardware-layout.standing.json`).
2. dev: `ssh -f -N -o ExitOnForwardFailure=yes -L 1884:localhost:1883 honeysuckle`.
3. honeysuckle, from the dev machine:
   `timeout 15 ssh -n honeysuckle 'cd ~/gridworks-scada/gw_spaceheat && setsid nohup timeout 300 venv/bin/python cli.py run > /tmp/hp-boss-boot.log 2>&1 < /dev/null &'`
4. dev, after ~40 s: with `HP_BOSS_DRIVE_SCADA=d1.bench.honeysuckle.scada
   HP_BOSS_DRIVE_PORT=1884 HP_BOSS_DRIVE_USER=bench HP_BOSS_DRIVE_PASS=<pi
   bench password>`, run `hp_boss_admin_drive.py admin-drive-honeysuckle.log`.
5. dev: `scp honeysuckle:/tmp/hp-boss-boot.log boot-honeysuckle.log`;
   read the relay's confirmed reports: `grep -n "hp-scada-ops-relay\|hp-boss\]" boot-honeysuckle.log`.
6. honeysuckle: `cp hardware-layout.standing.json hardware-layout.json`;
   dev: kill the tunnel.

**Pass.** Both drive legs show `hp-scada-ops-relay` confirming at the pin
(`OpenRelay` then `CloseRelay` reported to `admin.hp-boss`, no
enforcement retry), and LocalControl wakes to Normal on release.

## Rung 3 found: PASS on honeysuckle (2026-09-07, scada `3d871690`)

`admin-drive-honeysuckle.log` (admin side) and `boot-honeysuckle.log`
(scada side, pi clock, about 69 s behind the laptop's). Admin's TurnOff
reached `admin.hp-boss`, which sent OpenRelay to
`admin.hp-boss.hp-scada-ops-relay`; the relay, an `i2c.relay.component.gt`
on the gw108 with pin readback, committed `RelayOpen` 14 ms after
hp-boss reported `HpOff` (state list of the next snapshot: hp-boss
`1788794044096`, relay `1788794044110`). TurnOn: `HpOn` then
`RelayClosed` 12 ms later (`…056062`, `…056074`). Release: LocalControl
`Dormant -> Normal`. No glitch event was persisted on the pi
(`~/.local/share/gridworks/scada/event/2026-09-07…`, zero `glitch`
files) and the log holds no `Critical` or re-assert line, so neither
command needed the verify-loop retry. The known
`Trouble with SendLayout: 'NoneType' object has no attribute 'component'`
line appears on admin link-up, as on 2026-09-05.

Two passes were needed. The first pass proved the command path and the
release but its snapshot parser read `LatestReadingList`, where relay
states do not live (they ride `LatestStateList`); rung 2's empty
`hp-scada-ops-relay={}` lines have the same cause. The parser was fixed
and the second pass witnessed the states. Between the passes a second
scada was launched while the first was still inside its `timeout 300`;
both were killed and one clean boot made the witnessed pass. The first
pass's boot log was kept on the pi as `/tmp/hp-boss-boot-1.log` and is
not archived here.

Timeline (laptop clock): 11:09:53 first boot · 11:10:09–11:10:41 first
drive · 11:14:14 both scadas killed · 11:14:49 clean boot ·
11:15:12–11:15:45 witnessed drive · standing layout restored, tunnel
closed.
