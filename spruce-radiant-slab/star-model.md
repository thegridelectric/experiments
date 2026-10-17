# Star model for the slab when it is not being charged

> What this is: the model shape proposed for the slab at spruce, where it
> comes from in the literature, how to fit it from the journal data, and
> the three stages (slab without charging, charging, house) that build on
> each other. Research notes, 2026-10-15; nothing here is fitted yet.

## Why the two-lump model is not enough

The two-lump floor-and-room model in the README says the gap between
floor sensor and room decays at one rate, G over C, and never goes
negative. The spring spans in `no-charge-spans.md` show both to be false:
the apparent rate spreads from 0.05 to 0.3 per hour across events, and
after heating ended every floor settled 1 to 2 °F below its room and kept
falling for days. Heat is leaving the slab by a path other than the room.
Under a slab on grade that path is the ground.

## The model family in the literature

Thermally activated slabs (TABS, concrete core activation, radiant floors)
are modelled almost universally as a small resistance-capacitance network
around a core node at the tubing plane.

- Koschenz and Lehmann (Empa, 2000) give the charging side: fluid to pipe
  wall to core as three resistances in series, Rt = Rf + Rp + Rx.
- Weber and Jóhannesson (2005) make it transient as a star network: one
  core node with capacitance, a resistance up to the room surface, a
  resistance down to whatever is below, validated against measurements.
  The star form is limited to activated slabs, which is what we have.
- Hagentoft (1991) and Krarti's ITPE work treat the soil under a slab as
  a semi-infinite conductor: its response to a warm floor is a slow tail
  (t to the minus one half), not an exponential, and its mean
  temperature drifts with season. Over a few days a constant ground
  temperature behind one resistance is an adequate stand-in; a value
  fitted in October will not hold in April.
- Bacher and Madsen (2011) give the fitting method: write the network as
  stochastic differential equations, estimate by maximum likelihood with
  a Kalman filter, and climb a ladder of models (one lump, two lumps, plus
  ground) with likelihood-ratio tests until added structure stops paying.

With no charging the pipe branch of the star vanishes. What remains is
our situation exactly: a sensor at tubing depth, a sink above, a sink
below. The README's two-lump model is the star with the lower branch cut
off.

## The proposed model for spruce

All three zones share materials and tubing; they may differ in sensor
placement a little and in ground exposure more. So:

- **Shared slab, four parameters.** Two capacitances per zone (concrete
  above the tubing plane, concrete below), one resistance between them,
  one resistance from the upper node to the room. The sensor reads the
  lower node. Same values in every zone.
- **Ground, one resistance per zone** from the lower node to a ground
  temperature, with one ground temperature per season (per zone only if
  the fit demands it).
- **Inputs:** the zone's room temperature, as measured. Nothing else
  during a no-charge span.
- **Fit** jointly over every no-charge span, all zones at once, by
  maximum likelihood. Then free the slab parameters per zone and test
  whether the likelihood improves. If it does not, "same construction"
  is a result rather than an assumption.

Two features of the data make this well posed. The garage on 2026-04-27
(room steps down 12 °F, slab responds) and the bedrooms on 2026-04-04 are
natural step tests of the upper resistance. The post-season floats, where
every floor settles below its room and keeps falling, pin the ground
branch independently of the room branch. What comes out is a fast time
constant (hours, the tubing plane equilibrating with the slab), a slow one
(about half a day, the slab against the room) and the ground tail, in
place of a single G over C.

## What stage one covers and leaves out

Stage one is three slab models fitted together, each a slab against its
own room and its own patch of ground, on the no-charge spans only. It is
not a house model. Per zone it gives how fast the slab gives heat to the
room per degree of gap, how much the slab stores per degree at the
sensor, and how much it leaks to the ground; the slab part shared across
zones, the ground part separate. The room temperature is an input the
model is handed, not something it predicts.

Left out on purpose:

- The house: loss to outdoors, solar gain, the fan coils, and the room's
  response to the slab. The room is measured, so none of these are
  needed for this fit.
- Charging: the pipe-to-core branch of the star and what the sensor
  reads while hot water is in the tubing beside it.
- Zone-to-zone conduction through the shared floor. If the garage and
  living-room fits disagree in a way the ground term cannot absorb, this
  is where to look.

The no-charge spans are the one regime where the slab's own behaviour is
isolated: every input measured, nothing driving it but temperature
differences. Pinning the slab there first leaves the later stages with
one fewer unknown each.

## Fitting from the data

The Kalman form is what handles the things that hurt the spreadsheet
fit: a room-sensor dip becomes an innovation rather than a bias, gaps are
fine, and every span contributes. Tooling: the DTU group's CTSM-R does
this; a plain Python version (scipy least squares around a discrete
Kalman filter, five or six parameters) is a few hundred lines and stays
in this folder.

A simpler first pass that uses the sensors' resolution: integrate the
model over time instead of differentiating the data. For the one-lump
star, C (T(t) - T(0)) = -(1/R_up) ∫(T - T_room) dt - (1/R_g) ∫(T - T_g) dt,
which is linear in the unknowns at every sample time once T_g is taken
constant over a span. Cumulative trapezoid integrals at the native sample
times (one-minute temperatures, no binning) and ordinary least squares
give the parameters with no derivative estimate anywhere. The two-lump
version is the same idea applied to the state-space form.

## Checking against actuals, then the next two stages

Each stage reuses what the previous one pinned and has its own data
regime and its own check.

1. **Slab, no charging.** Fit on the no-charge spans; check by
   simulating every span forward from its start with the measured room
   temperature and comparing the floor trace. The pass mark is residuals
   with no shape: curvature in the first hours means a missing fast
   mode, drift over days means the ground term is wrong. Can be done now.
2. **Charging.** Add the pipe branch of the star: heat from the loop,
   metered on the hot side by the BTU meter, into the tubing node
   through one resistance shared across zones. Fit on charging hours
   with the slab parameters frozen. The check is the floor trace during
   and just after a charge, especially the relaxation from water
   temperature to concrete when flow stops. The sensor's position
   relative to the tubing is the one thing likely to differ by zone. If
   the sensor proves a poor proxy for the slab while charging, fit the
   slab's heat content from the BTU meter and the post-charge decay
   instead of the sensor peak. Spring charging data is thin (short
   calls, low flow, no room temperatures before Mar 30), so this stage
   mostly waits for this winter.
3. **House.** The room becomes a state: a room node with its own
   capacitance, a loss to outdoor temperature, the slab's heat into it,
   solar and the fan coils as inputs. Fit on everything, including the
   whole-house floats (Apr 4 to 6, Apr 30 to May 10). Actual outdoor
   temperature is in the journal only from Oct 7 (and Aug 13 to 27);
   the spring floats need backfilled Millinocket history or wait. This
   is where the model stops being a slab model and becomes a building
   model, and where adding one node at a time with a likelihood test
   matters most.

With all three, the Knife's Edge sizing question (how many hours of heat
a slab of this size stores on a design day) is a simulation, not a rule
of thumb.

## Found so far (2026-10-15, first fit)

`star_fit.py` fits the one-lump star by cumulative-integral least squares
on 54 no-charge spans (4484 h, three zones, both seasons) and writes
`star-fit.xlsx`: a Summary sheet and one sheet per span with the measured
floor, the forward-simulated floor and the room, charted. Forward RMS
0.77 °F over all spans, but the parameters are not physical, so the fit
is not accepted:

- Shared room conductance over capacitance 0.029 per hour (time constant
  about 34 h) against 0.0735 from the Oct 7 night alone; per-zone it
  spreads 0.013 to 0.042.
- The ground branch is unidentified: ground temperature 98 °F for the
  bedrooms, 8 °F for the living room, a negative conductance for the
  bedrooms. Restricting to spans with a real transient or weighting spans
  equally moves every number by factors of two and flips signs.
- Single spans fitted alone with a free room offset give rates from
  -0.07 to +0.11 per hour; the Oct 7 span gives 0.019 over its 41 h.
- A room-branch-only fit gives a negative conductance: the floor sits 1
  to 3 °F below its room most of the time and still falls, and in several
  spring spans it rises 5 °F while below the room (bedrooms and living
  room from Apr 24, garage Apr 23 to 26).

So a heat input the model does not have dominates the no-charge data.
Suspects, in order: sun on the slab (spring, south glass, floors rising
while below room); heat from the loop into a zone that is not calling
(manifold and neighbouring tubing under the same slab, the living room
during bedroom charges); and the room sensor not reading the air at the
floor, which is an offset the integral form absorbs only if it is
constant. The next step is to test these with the data in hand before
adding capacitances: compare floor rise against daylight hours and
against loop flow for other zones, and look at the Sep 23 to Oct 6
spans, where there was no loop at all and little sun on the floor.

### With measured irradiance (2026-10-16)

Measured horizontal irradiance from the Millinocket personal weather
station KMEMILLI18 (5-minute highs, W/m2; `irradiance-kmemilli18.csv`,
pulled by `pull_irradiance.py`, every day of the three windows present)
is now a model input: a solar gain `s` per zone, fitted as one more
column of the integral regression.

- The gain is positive in every zone and small: bedrooms 0.15, garage
  0.16, living room 0.24 °F per kWh/m2 of horizontal irradiance. A clear
  May day (6 kWh/m2) lifts the living-room floor about 1.4 °F, which is
  the midday hump seen in the hour-of-day means.
- Day by day the signal is weak: floor rise 09:00 to 17:00 against the
  day's irradiance correlates at r 0.34 (bedrooms), 0.22 (living room)
  and -0.17 (garage, which has no south glass); the night-time fall is
  of the same size as a sunny day's rise.
- The ground branch does not improve: conductances still negative for
  the bedrooms and living room, ground temperatures still unphysical,
  forward RMS 0.80 °F against 0.76 without sun. Spring-only and
  fall-only fits give solar gains that differ by factors of two to six.

So sun explains the daytime shape but not the standing fall of a floor
that reads below its room. What remains is the room sensor: four feet up
under the thermostat, reading about 2 °F above the air at floor level on
every night of both seasons (hour-of-day means, no-loop stretches). The
slab exchanges heat with air nothing measures, and a constant offset is
collinear with the ground term in this form. The way out is a slab-side
measurement of the top heat flow: the floor-surface sensors of Feb 6 to
Mar 10 (tubing-depth minus surface in the same concrete), or a
floor-level air or surface sensor added this winter.

## Sources

- Weber, Jóhannesson, "An optimized RC-network for thermally activated
  building components", Building and Environment 40 (2005).
  https://www.sciencedirect.com/science/article/abs/pii/S0360132304001544
- Weber, Jóhannesson, Koschenz, Lehmann, Baumgartner, "Validation of a
  FEM-program and a simplified RC-model for TABS using measurement data",
  Energy and Buildings (2005).
  https://www.sciencedirect.com/science/article/abs/pii/S0378778804003305
- Koschenz, Lehmann, "Thermoaktive Bauteilsysteme tabs", Empa 2000.
  https://books.google.com/books/about/Thermoaktive_Bauteilsysteme_tabs.html?id=Og1hNQAACAAJ
- Lehmann, Dorer, Koschenz, "Application range of thermally activated
  building systems", Energy and Buildings (2007).
  https://www.sciencedirect.com/science/article/abs/pii/S0378778806002349
- Bacher, Madsen, "Identifying suitable models for the heat dynamics of
  buildings", Energy and Buildings 43 (2011).
  https://backend.orbit.dtu.dk/ws/files/126769045/modelselection09.pdf
- Hagentoft, "Heat loss to the ground from a building, I. General
  theory", Building and Environment (1991).
  https://sciencedirect.com/science/article/pii/0360132391900279
- Krarti et al., "Experimental validation of an analytical model for
  transient heat transfer from slab-on-grade floors".
  https://www.osti.gov/etdeweb/biblio/20030563
- Deru, Kirkpatrick, "Ground-coupled heat and moisture transfer from
  buildings, part 2", NREL. https://docs.nrel.gov/docs/fy01osti/29694.pdf
- Multi-zone UKF grey-box identification. https://arxiv.org/pdf/1601.02947
- Zamani et al., UKF plus nonlinear least squares for RC models with a
  charged slab, 2025.
  https://journals.sagepub.com/doi/full/10.1177/1420326X241270775
- TABS grey-box model with Kalman filter for MPC, BS2023.
  https://publications.ibpsa.org/proceedings/bs/2023/papers/bs2023_1343.pdf
