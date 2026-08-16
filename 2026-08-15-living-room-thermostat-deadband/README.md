# Living-room fan-coil thermostat — deadband + when-it-stopped

Genre: observational analysis. Run 2026-08-15. Data pulled read-only from the
journal; nothing touched the running system. Harness:
[`analyze.py`](analyze.py) over [`living_room_week.csv`](living_room_week.csv).

## Why

George reported the living-room (zone-5) fan-coil thermostat "wasn't working."
Two questions: (1) how large is its deadband, and (2) when did it stop? Method
follows Thomas's falling-edge idea (scada `derived_generator.py`,
`simple-falling-edge-setpoint`: the setpoint is the zone temp at the FALLING
edge of a call) — read the living-room air temp (`zone2-living-rm-gw-temp`, the
same-room thermistor) at every call ON/OFF edge of
`zone5-living-rm-fancoil-heat-call` over the week before the 2026-08-15 scada
intervention, so the calls here are the WALL thermostat's, not ours.

## Found

**Working span:** 08-08 09:17 → 08-11 19:18 ET. 112 call cycles.

### (1) Deadband — too tight to resolve at the room sensor
- Call-ON edge temps: median **71.6°F** (70.8–73.1).
- Call-OFF edge temps: median **71.5°F** (69.5–74.1).
- Per-cycle swing (ON temp − OFF temp): **median 0.09°F** (p10 −0.04, p90 0.22).
- Cycle period: **median 32 min** — it short-cycled.

The room air barely moves per cycle (~0.1°F, within the thermistor's own
noise), so the thermostat's internal hysteresis is smaller than this sensor
can distinguish — it held the living room tightly around **~71.5°F**, cycling
the fan-coil about every half hour. That is far tighter than Thomas's assumed
`SetpointThresholdFX100 = 2.0°F` and tighter than our replacement's 1°F band.
(Caveat: the gw108 thermistor is not the thermostat's own sensor; room thermal
inertia attenuates whatever swing the thermostat sees internally. What we can
say firmly is the *room* was held within a fraction of a degree of 71.5°F.)

**Operating-point note for our replacement:** George's stat held ~71.5°F; our
folded-in thermostat targets 69.5–70.5°F — about 1.5°F colder. Worth a check
that 70°F is actually what he wants (he'd cranked the dead stat "all the way
down" trying to force it, so his true preference may be the ~71.5°F it held).

### (2) When it stopped — 08-11 19:18 ET
The last call ran 08-11 16:04 → **19:18** (a single ~3.2 h call, unlike the
~32 min short-cycles before it), then the channel went to "not calling" and
stayed there. **Dead ~92 h** through 08-15 14:59. During that interval the
living room climbed to **76.0°F — +4.4°F past the ~71.6°F it used to call at —
with no call at all.** That is the thermostat not responding, and it dates the
failure to the evening of **2026-08-11** (consistent with George's "~3 days").

## Reproduce

    # pull (read-only) — GJK_DB_URL in ../.env:
    psql "$GJK_URL" -tA -F',' -c "select extract(epoch from r.timestamp)::bigint,
      rc.name, r.value from gridworks.reading_channels rc
      join gridworks.readings r on r.channel_id=rc.id
      where rc.terminal_asset_alias='hw1.isone.me.versant.keene.spruce.ta'
      and rc.name in ('zone2-living-rm-gw-temp','zone5-living-rm-fancoil-heat-call')
      and r.timestamp between now()-interval '8 days'
        and timestamp with time zone '2026-08-15 15:00-04' order by r.timestamp" \
      > living_room_week.csv
    python3 analyze.py
