#!/usr/bin/env python3
"""Pico link-type census (READ-ONLY): wired (Wiznet ethernet) vs wifi
(Pico W) picos per house, from each house pi's neighbor table.

Method: every pico shares a LAN with its house pi; the MAC's first three
bytes (OUI) name the manufacturer. WIZnet ethernet modules carry
00:08:dc; Pico W wifi boards carry a Raspberry Pi OUI (28:cd:c1 /
2c:cf:67 / d8:3a:dd — shared with recent pi computers, so known pi
hosts are excluded by their own interface MACs before counting).

Run from a machine with ssh access to the house pis (BatchMode keys).
Neighbor tables only show recently-active devices; picos post
continuously, so active picos appear. A pico that is offline right now
is missed — re-run at another time to catch stragglers.
"""

import subprocess
import sys

HOUSES = {
    "beech": ["beech", "beech2"],
    "elm": ["elm", "elm2"],
    "fir": ["fir", "fir2"],
    "maple": ["maple", "maple2"],
    "oak": ["oak", "oak2"],
    "spruce": ["spruce"],
}

WIZNET_OUIS = {"00:08:dc"}
RPI_OUIS = {"28:cd:c1", "2c:cf:67", "d8:3a:dd", "b8:27:eb", "dc:a6:32", "e4:5f:01"}


def ssh(host: str, cmd: str) -> str:
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, cmd],
        capture_output=True, text=True, timeout=30,
    )
    return r.stdout


def main() -> int:
    print(f"{'house':8} {'pi':8} {'wired(wiznet)':>14} {'rpi-family':>11} {'other':>6}")
    totals = {"wired": 0, "rpi": 0}
    for house, hosts in HOUSES.items():
        for host in hosts:
            try:
                neigh = ssh(host, "ip neigh show")
                own = ssh(host, "cat /sys/class/net/*/address").split()
            except Exception as e:
                print(f"{house:8} {host:8} unreachable ({e})")
                continue
            own_macs = {m.lower() for m in own}
            wired, rpi, other = [], [], []
            seen = set()
            for line in neigh.splitlines():
                parts = line.split()
                if "lladdr" not in parts:
                    continue
                mac = parts[parts.index("lladdr") + 1].lower()
                ip = parts[0]
                if mac in own_macs or mac in seen:
                    continue
                seen.add(mac)
                oui = mac[:8]
                if oui in WIZNET_OUIS:
                    wired.append((ip, mac))
                elif oui in RPI_OUIS:
                    rpi.append((ip, mac))
                else:
                    other.append((ip, mac))
            print(f"{house:8} {host:8} {len(wired):>14} {len(rpi):>11} {len(other):>6}")
            for ip, mac in wired:
                print(f"{'':17} wired  {ip:16} {mac}")
            for ip, mac in rpi:
                print(f"{'':17} rpi    {ip:16} {mac}")
            totals["wired"] += len(wired)
            totals["rpi"] += len(rpi)
    print(f"\nfleet: {totals['wired']} wiznet(wired) · {totals['rpi']} rpi-family "
          "(pico-w OR another pi — cross-check known pi hosts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
