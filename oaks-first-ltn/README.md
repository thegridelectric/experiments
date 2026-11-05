# oaks-first-ltn

> What this is: the record of how oak has run on the first field LTN
> (the FLO on `td/bruce`), read off the LTN box log and the journal
> DB, with the findings so far and the questions still open. The first
> pull is the box log for 2026-11-01 14:00 to 00:10 Eastern,
> `oak-ltn-log-2026-11-01.txt`. The folder spans several days; the
> analysis session adds to it, the patching session on OPS-392 takes
> fixes from it.

## Why

Oak is the first house whose bids come from a FLO running in the field
rather than a simulation. Whether the optimizer's plan, the bid sweep
and the clearing rule behave as designed can only be read off a real
day, and the fixes on OPS-392 and the harness for OPS-514 both need
that reading before they can claim to reproduce it.

## Setup

- **LTN box log.** `ssh ltn`, then `journalctl -u gwltn@oak.service`.
  The box clock is America/New_York, so every log time is Eastern. The
  2026-11-01 14:00 to 00:10 excerpt, with the once-a-minute lines
  dropped by hand, is `oak-ltn-log-2026-11-01.txt` beside this file;
  its provenance is the `.provenance.txt` sidecar.
- **Deployed code on the box.** `/home/ubuntu/ltn-oak/gridworks-scada`
  at `f1491b3c` and `/home/ubuntu/ltn-oak/optimal-flexibility` at
  `2711f59`. Oak's ops word and layout are in
  `/home/ubuntu/ltn-oak/.config/gridworks/ltn/`.
- **Journal DB.** `spot_check.py --house oak` over the same window, in
  Eastern. The journal has no contract word; a contract is visible only
  through `gw1.leaf.ally.buffer.only.state` transitions and the
  `hp-odu-pwr` channel.
- **What is missing.** The params each FLO run was given were not
  journaled: the box logs "Non-critical SCADA MQTT publish skipped
  (HeatPumpWaterTankParams): payload has no TypeName" at every bid. The
  weather forecast pull fails on `Version` (the forecast box serves
  `gw.weather.forecast` 002, the box expects 001), so every run used
  the seasonal template for outdoor temperature and load.

## 2026-11-01, 15:00 to 23:00 Eastern

Every bid was one pair at the price floor of -100 $/MWh. The store
temperatures are the `AllTanks model` line at :05 (top, middle,
bottom °F); the plan is the `HourlyHpKwhElPlan` logged at :00 of the
slot, whose index 0 is the hour after the slot. "Used" is the scada's own energy accounting
at contract close.

| Slot | Store at :05 | Bid Wh at floor | Cleared $/MWh | Contract | Used | HP ODU mean | Plan made at :00, next 8 h (kWh el) |
|---|---|---|---|---|---|---|---|
| 15:00 | 167 / 157 / 148 | | | | | | 0 0 0 0 0 7.6 0 0 |
| 16:00 | 166 / 156 / 144 | | | 0 | 124 | | 0 0 0 0 7.1 0 0 0 |
| 17:00 | 164 / 154 / 141 | 0 | | 0 | 155 | 144 W | 0 0 0 0 0 7.7 2.3 0 |
| 18:00 | 162 / 152 / 138 | 4 | | 0 | 37 | 26 W | 0 0 0 0 7.7 2.0 0 0 |
| 19:00 | 161 / 150 / 136 | 16 | | 0 | 37 | 25 W | 0 0 0 7.2 0 0 0 0 |
| 20:00 | 159 / 149 / 133 | 13 | 87.49 | 0 | 37 | 26 W | 0 0 6.7 0 0 0 0 0 |
| 21:00 | 157 / 147 / 131 | 13 | 86.23 | 0 | 37 | 26 W | 0 5.7 0 0 0 0 0 7.8 |
| 22:00 | 151 / 143 / 141 | 3416 | 86.09 | 3416 | 3580 | 2182 W | 4.5 0 0 0 0 0 7.8 0 |
| 23:00 | 174 / 164 / 158 | 0 | 87.42 | 0 | | 25 W | 0 0 0 0 0 7.7 3.0 0 |

The 22:00 contract was honoured: the leaf ally went HpOn at 22:00:00
and HpOff at 22:38, and the scada counted 3580 Wh against 3416.

## Findings

1. **The bid sweep on the box drops every quantity decrease.** The
   deployed `generate_bid` climbs from the floor and records a pair only
   when the quantity rises by more than 0.01 kWh. A demand curve falls
   with price, so the pair at the floor is the only one that survives.
   This is why every bid is one pair at -100 $/MWh. Fixed on the
   GridWorks fork of optimal-flexibility at `9ecc3aa` (sweep from the
   ceiling, keep every change), with a test that the curve has more
   than one segment. It is not deployed to oak.

2. **The FLO's store ceiling is the heating curve's maximum EWT, 161 °F
   at oak.** The LTN sets bruce's `max_tank_temp_f` from
   `HeatingCurve.MaxEwtF`, and bruce refuses any charging transition
   that would take the store above that temperature in every layer.
   From 15:00 to 19:00 the store top was at or above 161 °F, so the
   model had no room to buy into at any price, including the floor.
   That is the answer to "why did the FLO not want to be paid to heat":
   it believed the store was full. Whether the ceiling should be the
   emitter's maximum supply temperature or the store's physical maximum
   is a design question for the FLO boundary; the scada's own control
   evidently takes the store past 161 °F.

3. **With room, the short-cycle penalty decides at the floor.** By 21:57
   the store had room for a few kWh. A charge in hour 0 pays the
   short-cycle penalty, the horizon's median price times a weight of 6
   times the unused fraction of the heat pump's hour. For a 3.4 kWh
   run against a 7.7 kWh maximum that is about $0.29, while buying
   3.4 kWh at -100 instead of 86 $/MWh is worth about $0.63, so the run
   wins. An hour earlier the room was smaller, the fraction smaller,
   the penalty larger, and the gain smaller, so it lost. The penalty
   arithmetic is in `asset.py` `short_cycle_penalty`; the hour-0
   maximum is 0.8 times `HpMaxKwEl` 9.66 because `hp_turn_on_minutes`
   is 12.

4. **The 4, 13 and 16 Wh quantities are a modelling residue.** bruce's
   hour-0 electricity is max(0, load + losses + heat to store) over
   COP. A "serve the load from the store" action on the discrete state
   grid does not cancel the load exactly and a few watt-hours of slack
   get charged to the heat pump. The LTN zeroes anything under 1000 Wh
   before it becomes a contract, so no harm today, but a bid should
   say 0.

5. **The bid and the plan are for different hours.** The plan is
   `next_node.shortest_path_elec`, the electricity on the path onward
   from the node at time step 1, so index 0 is the hour after the bid
   slot. The 22:00 bid of 3416 Wh (22:00 to 23:00) and the 4.5 kWh at
   index 0 of the plan made at 22:00 (23:00 to 00:00) do not disagree.
   The LTN feeds that plan back as `previous_plan_hp_kwh_el_list` for
   the next run, where index 0 is again hour 0, so the alignment holds.

6. **The LTN's clearing rule reads the wrong segment.** It takes the
   highest-priced pair strictly below the cleared price; bruce's pairs
   hold for prices in (next lower price, this price], so the right pair
   is the lowest-priced one at or above the cleared price. With one
   pair per bid the rule is moot, which is why nothing has gone wrong
   yet.

## Found

Open. The findings above are read off the log and the deployed code;
none has yet been reproduced by running the FLO on the day's inputs.

## Open

- The planned charge walks toward the present one hour per run (hour
  5, 4, 5, 4, 3, 2, 1, 0) and shrinks as it comes (7.6, 7.1, 7.7, 7.7,
  7.2, 6.7, 5.7, 4.5). The drift is the FLO deferring to the cheapest
  forecast hour as the store drains; the shrinking is not explained.
  The stability penalty (weight 0.5, decay 0.75 per hour) is the first
  suspect.
- The FLO's storage figure (175 to 180 kWh) and the scada's
  `usable-energy` channel (13 to 21 kWh) measure different things; the
  write-up should say which, before either is quoted.
- Reproducing a run needs the params the box did not journal. The
  pieces are all on the box: the store temperatures in the log, the
  saved `price_forecast.csv`, the seasonal template, oak's ops word and
  layout, and the previous plan from the log line before. The run
  belongs in the `test_ltn.py` round trip against the forked bruce.

## Folder contents & experimental method

The data is the LTN box's own log, read with `journalctl` over ssh and
reduced to the lines that name a bid, a contract, a plan or a store
model; the journal DB was read with `spot_check.py` for the heat pump
power, the usable energy and the leaf-ally state in the same window.
Nothing here was run on the box.

- `README.md`: this record.
- `oak-ltn-log-2026-11-01.txt`: EXTERNAL EVIDENCE, the LTN box log for
  2026-11-01 14:00 to 00:10 Eastern with the once-a-minute lines
  dropped by hand; the sidecar
  `oak-ltn-log-2026-11-01.provenance.txt` says where it came from. The
  full log is still on the box's journal; the pull, from the laptop:

      ssh -n ltn 'journalctl -u gwltn@oak.service --no-pager --since "2026-11-01 14:00" --until "2026-11-02 00:10"'

  The reduction has no script; a re-pull is the full log.
