#!/usr/bin/env bash
# The commands run on spruce for the Rev C bench window, in order. Run
# from the laptop; the scada service on spruce is stopped throughout.
set -euo pipefail

# 1. Baseline reads (actuate nothing): bus scan, native inputs, expanders.
ssh spruce 'cd ~/starter-scripts && i2cdetect -y 1 && venv/bin/python - <<"PY"
import gw108_test_code as g
g.print_zones(); print("shutdown", g.GPIO.input(g.GPIO_SHUTDOWN)); print("valve4 energized", g.valve_4_energized()); g.print_expanders()
PY'

# 2. ADC and DAC reads (actuate nothing).
ssh spruce 'cd ~/starter-scripts && venv/bin/python - <<"PY"
import gw108_test_code as g
for i,ch in enumerate(g.THERM_CHANNELS,1): print(f"th{i} {ch.voltage:.3f} V {g.get_temp_f(i)}")
for i,ch in enumerate([g.ct1,g.ct2,g.ct3,g.ct4],1): print(f"ct{i} {ch.voltage:.3f} V")
for n,d in enumerate([g.dac1,g.dac2,g.dac3],1): print(f"dac{n}", [c.raw_value for c in (d.channel_a,d.channel_b,d.channel_c,d.channel_d)])
PY'

# 3. The pico API for the window (picos post to port 8000) and the zone watch.
ssh spruce 'cd ~/starter-scripts && setsid nohup ./start_api.sh > /tmp/pico_api.log 2>&1 < /dev/null & disown'
ssh spruce 'setsid nohup /home/pi/starter-scripts/venv/bin/python /tmp/zone_watch.py > /tmp/zone_watch.log 2>&1 < /dev/null & disown'
# /tmp/zone_watch.py: read BCM 17 27 22 10 9 11 once a second, print each change with a timestamp.

# 4. Collect the logs.
scp spruce:/tmp/zone_watch.log evidence/zone_watch.log
scp spruce:/tmp/pico_api.log evidence/pico_api.log

# 5. Window 3: CT reads from one process (relays survive import at ff10ea7).
#    Scripts in evidence/ct-window3/: ct_probe.py (all four channels),
#    ct2_sweep.py (Dac3 C sweep, edit the channel), ct1_store_sweep.py and
#    ct1_store_once.py (Valve 1 + Pump 2 held, ct1 sampled, released).
scp evidence/ct-window3/ct1_store_once.py spruce:/tmp/
ssh spruce 'cd ~/starter-scripts && PYTHONPATH=. venv/bin/python /tmp/ct1_store_once.py'
scp 'spruce:/tmp/ct1_store_1turn_*.csv' evidence/ct-window3/ && ssh spruce 'rm -f /tmp/ct1_store_*'
