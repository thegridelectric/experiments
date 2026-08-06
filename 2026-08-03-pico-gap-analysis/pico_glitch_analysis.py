#!/usr/bin/env python3
"""Pico health via SCADA GLITCHES (READ-ONLY) — the second angle.

The gap analysis infers pico dropouts from reporting silence; this
queries what the scadas THEMSELVES reported: `glitch` messages in the
analytics DB (gridworks.messages, payload jsonb) with the pico-health
summaries — `pico-just-zombied` (a pico flatlined through the VDC reboot
cycles) and `pico-zombies` (the periodic zombie roster; pico ids in
Details).

Run with GJK_DB_URL set to the analytics postgres URL (psycopg).
  WINDOW_DAYS=56 ./pico_glitch_analysis.py
"""

import os
import re
import sys
from collections import Counter, defaultdict

import psycopg

WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "14"))
PICO_SUMMARIES = ("pico-just-zombied", "pico-zombies")


def main() -> int:
    url = os.environ["GJK_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(url)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT m.from_alias, m.payload->>'Summary',
               m.payload->>'Node', m.payload->>'Details',
               m.timestamp AT TIME ZONE 'America/New_York'
        FROM gridworks.messages m
        WHERE m.message_type_name = 'glitch'
          AND m.timestamp > now() - interval '1 day' * %s
        """,
        (WINDOW_DAYS,),
    )
    rows = cur.fetchall()
    conn.close()

    def house(alias: str) -> str:
        m = re.search(r"\.([a-z0-9]+)\.scada$", alias or "")
        return m.group(1) if m else (alias or "?")

    by_house = defaultdict(Counter)
    pico_glitches = defaultdict(Counter)
    zombie_picos = defaultdict(Counter)
    zombie_nodes = defaultdict(Counter)
    for alias, summary, node, details, ts in rows:
        h = house(alias)
        by_house[h][summary] += 1
        if summary in PICO_SUMMARIES:
            pico_glitches[h][summary] += 1
            for pico in re.findall(r"pico_[0-9a-f]+", details or ""):
                zombie_picos[h][pico] += 1
            if summary == "pico-just-zombied" and node:
                zombie_nodes[h][node] += 1

    print(f"Glitch census, last {WINDOW_DAYS} days "
          f"(gridworks.messages, {len(rows)} glitch rows)\n")
    print("== pico-health glitches by house ==")
    for h in sorted(by_house):
        pico_n = sum(pico_glitches[h].values())
        detail = "  ".join(f"{s}={n}" for s, n in pico_glitches[h].items())
        print(f"  {h:8} pico-glitches={pico_n:>4}  {detail}")
    print("\n== zombie picos (from Details) ==")
    for h in sorted(zombie_picos):
        for pico, n in zombie_picos[h].most_common():
            print(f"  {h:8} {pico}  x{n}")
    print("\n== pico-just-zombied by actor node ==")
    for h in sorted(zombie_nodes):
        for node, n in zombie_nodes[h].most_common():
            print(f"  {h:8} {node}  x{n}")
    print("\n== all glitch summaries by house (context, top 6 each) ==")
    for h in sorted(by_house):
        tops = "  ".join(f"{s}×{n}" for s, n in by_house[h].most_common(6))
        print(f"  {h:8} {tops}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
