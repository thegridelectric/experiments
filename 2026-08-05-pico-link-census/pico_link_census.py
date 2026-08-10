#!/usr/bin/env python3
"""Pico link-type census (READ-ONLY): wired (Wiznet ethernet) vs wifi
(Pico W) picos per house, from each house pi's neighbor table.

Method: every pico shares a LAN with its house pi; the MAC's first three
bytes (OUI) name the manufacturer. WIZnet ethernet modules carry
00:08:dc; Pico W wifi boards carry a Raspberry Pi OUI (28:cd:c1 /
2c:cf:67 / d8:3a:dd — shared with recent pi computers, so known pi
hosts are excluded by their own interface MACs before counting).
NOTE (found after the first run): the deployed ethernet firmware brings
up WIZNET5K with no explicit MAC, so wired picos do NOT carry the
WIZnet OUI — the census observes MACs but cannot conclude link type.

Run from a machine with ssh access to the house pis (BatchMode keys).
Neighbor tables only show recently-active devices; picos post
continuously, so active picos appear. A pico that is offline right now
is missed — re-run at another time to catch stragglers.

MAC values are vocabulary-shaped: the registry's `mac.address` format
covers them, but it is not yet in the vendored snapshot (formats
arrive only as dependencies of seeded types; vendor it with the next
snapshot regen). Until then they ride as plain lowercase strings.
"""

import subprocess
import sys
from typing import NamedTuple

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


class Neighbor(NamedTuple):
    """One LAN neighbor observed in a house pi's `ip neigh` table:
    `mac` lowercase colon-separated (`mac.address`-shaped, see module
    docstring), classified by its OUI prefix."""
    ip: str
    mac: str


def ssh(host: str, cmd: str) -> str:
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, cmd],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1]
                           if r.stderr.strip() else f"ssh exit {r.returncode}")
    return r.stdout


def neighbors(neigh_output: str, own_macs: set[str]) -> list[Neighbor]:
    """Parse `ip neigh show` into deduplicated neighbors, excluding the
    pi's own interfaces."""
    out: list[Neighbor] = []
    seen: set[str] = set()
    for line in neigh_output.splitlines():
        parts = line.split()
        if "lladdr" not in parts:
            continue
        mac = parts[parts.index("lladdr") + 1].lower()
        if mac in own_macs or mac in seen:
            continue
        seen.add(mac)
        out.append(Neighbor(ip=parts[0], mac=mac))
    return out


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
            found = neighbors(neigh, {m.lower() for m in own})
            wired = [n for n in found if n.mac[:8] in WIZNET_OUIS]
            rpi = [n for n in found if n.mac[:8] in RPI_OUIS]
            other = [n for n in found
                     if n.mac[:8] not in WIZNET_OUIS and n.mac[:8] not in RPI_OUIS]
            print(f"{house:8} {host:8} {len(wired):>14} {len(rpi):>11} {len(other):>6}")
            for n in wired:
                print(f"{'':17} wired  {n.ip:16} {n.mac}")
            for n in rpi:
                print(f"{'':17} rpi    {n.ip:16} {n.mac}")
            totals["wired"] += len(wired)
            totals["rpi"] += len(rpi)
    print(f"\nfleet: {totals['wired']} wiznet(wired) · {totals['rpi']} rpi-family "
          "(pico-w OR another pi — cross-check known pi hosts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
