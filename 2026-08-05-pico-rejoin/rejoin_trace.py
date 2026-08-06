"""rejoin_trace.py — time a Pico W's wifi join after power cycles.

Deliberately mirrors the deployed firmware's join path (ONE
wlan.connect(), then wait) so what gets measured is the schedule of
the layers below: the CYW43 driver's internal join retries and DHCP.

Copy to the pico as main.py (`mpremote cp rejoin_trace.py :main.py`),
power-cycle at will, then read the log (`mpremote cat rejoin_log.txt`).
Prints to serial too when tethered (`mpremote run rejoin_trace.py`).

Uses WifiName/WifiPassword from comms_config.json when present (so a
deployed pico needs no edits); else the constants below.
"""

import network
import ujson
import utime

WIFI_NAME = "CHANGE_ME"
WIFI_PASSWORD = "CHANGE_ME"
LOG_FILE = "rejoin_log.txt"
HEARTBEAT_MS = 300_000

try:
    with open("comms_config.json") as f:
        _cfg = ujson.load(f)
    WIFI_NAME = _cfg.get("WifiName", WIFI_NAME)
    WIFI_PASSWORD = _cfg.get("WifiPassword", WIFI_PASSWORD)
except (OSError, ValueError):
    pass

STATUS_NAMES = {
    getattr(network, n): n for n in dir(network) if n.startswith("STAT_")
}

t0 = utime.ticks_ms()


def log(msg):
    line = "t=%8d ms  %s" % (utime.ticks_diff(utime.ticks_ms(), t0), msg)
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def rssi(w):
    try:
        return w.status("rssi")
    except Exception:
        return "?"


log("=== boot: single wlan.connect to %r, then watch ===" % WIFI_NAME)
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_NAME, WIFI_PASSWORD)

last_status = None
last_beat = t0
while True:
    s = wlan.status()
    if s != last_status:
        log("status -> %s (%s)" % (s, STATUS_NAMES.get(s, "?")))
        if s == network.STAT_GOT_IP:
            log("ip=%s rssi=%s" % (wlan.ifconfig()[0], rssi(wlan)))
        last_status = s
    now = utime.ticks_ms()
    if utime.ticks_diff(now, last_beat) > HEARTBEAT_MS:
        log("heartbeat: status=%s rssi=%s" % (s, rssi(wlan)))
        last_beat = now
    utime.sleep_ms(100)
