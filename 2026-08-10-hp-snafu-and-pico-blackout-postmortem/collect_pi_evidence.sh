#!/usr/bin/env bash
# Capture the spruce pi's own record of the blackout into evidence/
# (READ-ONLY over ssh; `spruce` from ~/.ssh/config, tailscale).
#
# These captures are EXTERNAL EVIDENCE, not immutable-store data: the
# journal excerpts are stable for the incident window while the pi's
# journald retains them, but the wifi/network state is point-in-time —
# a re-run after the router recovers records a DIFFERENT (healthy)
# state and must not overwrite the incident capture. Refuses to
# overwrite for that reason.
set -euo pipefail
cd "$(dirname "$0")/evidence"

stamp() {
    echo "# EXTERNAL EVIDENCE — captured $(date '+%Y-%m-%d %H:%M:%S %Z') over ssh from the spruce pi (100.69.205.1)."
    echo "# Command: $1"
    echo
}

capture() { # $1 = outfile, $2 = remote command
    if [ -e "$1" ]; then
        echo "SKIP $1 exists (incident captures are frozen; delete deliberately to re-capture)"
        return
    fi
    { stamp "$2"; ssh -o BatchMode=yes spruce "$2"; } > "$1"
    echo "wrote $1"
}

capture pi-journal-pico-cycler.log \
    'journalctl -u gwspaceheat --since "2026-08-10 16:55" --until "2026-08-10 17:25" --no-pager | grep pico-cycler'

capture pi-journal-summer-hack-evening.log \
    'journalctl -u spruce-summer-hack --since "2026-08-10 19:50" --until "2026-08-10 22:30" --no-pager'

capture pi-journal-brcmfmac.log \
    'journalctl -k --since "2026-08-10 12:00" --no-pager | grep brcmfmac | head -40; echo "[...continuous through:]"; journalctl -k --no-pager | grep "set chanspec" | tail -2'

capture pi-journal-networkmanager.log \
    'journalctl -u NetworkManager --since "2026-08-10 16:50" --until "2026-08-10 17:20" --no-pager | grep -iE "wlan0|GridWorks|disconnect"'

capture pi-wifi-state.txt \
    'echo "== nmcli connection show GridWorks (timestamp = last successful association) =="; nmcli -f connection.id,connection.timestamp,802-11-wireless.seen-bssids connection show GridWorks; echo; echo "== nmcli dev status =="; nmcli dev status; echo; echo "== wifi scan (2.4 GHz GridWorks BSSID 62:7F:F0:3B:2C:27 absent; 5 GHz sibling 66:...:21 beaconing) =="; nmcli dev wifi list; echo; echo "== ip neigh (pico MACs 28:cd:c1:* stale/failed; router + eGauge reachable) =="; ip neigh; echo; echo "== ping sweep =="; for ip in 1 51 131 78 202 74 67; do ping -c2 -W2 -q 192.168.2.$ip >/dev/null 2>&1 && echo "192.168.2.$ip UP" || echo "192.168.2.$ip no reply"; done'
