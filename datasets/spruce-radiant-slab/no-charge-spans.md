# Spruce: floor and room while the floor is not being charged

> What this is: every span of two hours or more in which a slab zone's
> floor was not being charged (the zone not calling with loop flow), with
> the floor and room temperatures at the start and end. Spring is Mar 30
> to May 16 2026 (room temperatures exist from Mar 30; the layout drops
> the floor-temp words on May 18), fall is Sep 23 to Oct 15 2026. Rows
> kept: gap at start at least 1 °F or gap at any time at least 2 °F,
> sorted by the largest gap seen. Hours with `+` run to the edge of a
> pull. Ten-minute bin means of the journal readings; nothing fitted.

Source: journal DB, `hw1.isone.me.versant.keene.spruce.ta` channels
`zone{1,2,4}-*-floor-temp`, `zone{1,2,4}-*-gw-temp`, `zone*-heat-call`,
`dist-flow`, pulled 2026-10-15 with `pull_readings.py`. "Charging" is any loop
flow (above 0.05 gpm) with the zone's heat call on; a charging blip under an
hour does not end a span.

Read with care:

- Garage 2026-04-27: the room fell from 80 to 68 °F in the hour after the
  call ended (a door, most likely), which is the 17 °F gap; the room was
  back at 77 by 17:00. After Apr 28 the garage floor sits 1 to 2 °F below
  its room and keeps falling for five days.
- Bedrooms 2026-04-04: the room sensor read 7 °F low for two hours at
  14:00 with the floor trace smooth; the 8.9 gap is that dip.
- Living room 2026-05-05: the room sensor jumped to 74 °F at the start and
  dipped to 56 °F twice; the floor sat below the room for the rest of May.
- Living room 2026-03-31 and 2026-04-08: the loop ran for other zones
  (bedrooms) part of the time; the living room floor itself was not called.

| zone | no charge from (ET) | hours | floor start °F | room start °F | gap start | gap max | floor end | room end | gap end |
|---|---|---|---|---|---|---|---|---|---|
| garage | 2026-04-27 05:50 | 79 | 84.8 | 80.2 | 4.6 | 17.4 | 70.3 | 72.1 | -1.8 |
| bedrooms | 2026-04-04 00:20 | 82 | 76.5 | 73.2 | 3.2 | 8.9 | 62.8 | 63.4 | -0.7 |
| living room | 2026-03-31 16:40 | 162 | 69.2 | 62.7 | 6.5 | 7.6 | 62.8 | 63.4 | -0.6 |
| living room | 2026-04-30 13:50 | 119 | 68.0 | 70.1 | -2.2 | 7.3 | 60.6 | 65.1 | -4.5 |
| living room | 2026-04-08 17:00 | 135 | 66.9 | 61.3 | 5.6 | 6.5 | 62.8 | 63.7 | -0.9 |
| garage | 2026-04-08 17:00 | 368 | 65.0 | 68.2 | -3.2 | 6.3 | 61.4 | 62.9 | -1.4 |
| living room | 2026-04-14 14:10 | 211 | 67.4 | 65.0 | 2.4 | 5.9 | 60.0 | 63.2 | -3.3 |
| living room | 2026-05-05 14:50 | 186 | 60.9 | 73.8 | -12.8 | 5.6 | 60.1 | 61.1 | -1.0 |
| living room | 2026-05-13 14:20 | 20 | 65.5 | 63.9 | 1.6 | 4.4 | 65.3 | 63.5 | 1.8 |
| garage | 2026-04-26 17:40 | 4 | 84.7 | 80.5 | 4.2 | 4.3 | 83.5 | 80.1 | 3.4 |
| living room | 2026-10-07 17:40 | 41 | 79.2 | 75.6 | 3.7 | 3.7 | 71.8 | 72.3 | -0.5 |
| bedrooms | 2026-09-23 00:00 | 327+ | 72.6 | 74.2 | -1.6 | 3.7 | 67.9 | 69.2 | -1.3 |
| garage | 2026-09-23 00:00 | 105+ | 68.9 | 72.7 | -3.7 | 3.2 | 68.8 | 70.2 | -1.4 |
| garage | 2026-04-30 13:50 | 119 | 70.3 | 72.3 | -2.0 | 3.0 | 62.0 | 65.6 | -3.6 |
| living room | 2026-05-14 12:00 | 60+ | 66.1 | 64.1 | 1.9 | 2.5 | 65.0 | 68.1 | -3.1 |
| bedrooms | 2026-04-08 17:50 | 15 | 64.6 | 65.0 | -0.4 | 2.0 | 63.8 | 61.8 | 2.0 |
| living room | 2026-10-14 10:00 | 30+ | 69.5 | 68.0 | 1.5 | 1.7 | 69.1 | 69.4 | -0.3 |
