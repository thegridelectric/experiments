# pico-rejoin

**Why.** After every half-hourly VDC shake at spruce, the secondary
flow pico goes silent for a stereotyped 13–14 min before reporting
again. The deployed wifi firmware cannot be the timer: it issues ONE
`wlan.connect()` and waits forever — no timeout, no retry, no
watchdog. So the 13–14 min is set below the firmware. Candidate
schedules: (a) the CYW43 driver's internal join retries, (b)
association/DHCP under the all-picos-at-once rejoin herd after a bus
power cycle, (c) no schedule at all — a terminal driver state (e.g.
bad-auth) rescued only by the next shake. (c) predicts ~30 min
silences, which the stereotyped 13–14 min already disfavors as the
common case. Whatever schedule wins also sets the timeout a
bounded-retry firmware fix should use.

**Setup.** `rejoin_trace.py` mirrors the deployed join path (single
connect, no retry) and logs every `wlan.status()` transition with ms
timestamps — to serial and to `rejoin_log.txt` on flash, so
untethered DC power cycles keep their traces. Takes
WifiName/WifiPassword from `comms_config.json` when present (a
deployed pico needs no edit); else edit the constants.

Run: `mpremote cp rejoin_trace.py :main.py`, power-cycle at will,
`mpremote cat rejoin_log.txt`. Tethered: `mpremote run
rejoin_trace.py`.

**Protocol.**

1. Baseline — any healthy Pico W + home router: ≥5 power cycles;
   collect time-to-association and time-to-GOT_IP per cycle.
2. Failure injections — wrong password (expect terminal
   `STAT_WRONG_PASSWORD`: the forever-hang, demonstrated); AP off at
   boot, powered on ~2 min later (does the driver's internal retry
   find it, and on what schedule?).
3. Spruce — the sick secondary pico across a real VDC shake (site
   visit; the trace temporarily replaces its main.py). Comparing its
   schedule against baseline splits pico vs router vs herd.

Follow-up variant once the schedule is known: the same trace with a
bounded re-`connect()`/reset loop, to verify the fix caps recovery.

**Found.** Open — not yet run.
