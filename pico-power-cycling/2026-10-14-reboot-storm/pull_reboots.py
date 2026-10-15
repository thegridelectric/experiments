"""Per-house, per-day pico-cycler bus reboots (transitions INTO RelayOpening)
and per-pico flatlines (transitions INTO Flatlined on single.pico.state),
from journal report.event payloads. Days are ET calendar days.
Run from experiments/:  uv run python <this file>
"""
import csv, datetime, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg
from spot_check import db_url, KNOWN_HOUSES, ET, collapse

OUT = Path(__file__).parent
HOUSES = ["maple", "oak", "spruce", "beech", "elm", "fir"]
START = datetime.date(2026, 9, 1)
END = datetime.date(2026, 10, 14)  # inclusive (partial today)
ENUMS = ("pico.cycler.state", "single.pico.state")

def day_ms(d):
    return int(datetime.datetime.combine(d, datetime.time(), ET).timestamp() * 1000)

def main():
    days = [START + datetime.timedelta(n) for n in range((END - START).days + 1)]
    reb_rows, flat_rows, rep_rows = [], [], []
    with psycopg.connect(db_url()) as conn:
        conn.read_only = True
        cur = conn.cursor()
        for house in HOUSES:
            alias = KNOWN_HOUSES[house]
            series: dict[tuple[str, str], list] = {}
            reports = Counter()
            for d in days:
                a, b = day_ms(d), day_ms(d + datetime.timedelta(1))
                cur.execute("""SELECT count(*) FROM gridworks.messages
                    WHERE from_alias=%s AND message_type_name='report.event'
                      AND timestamp >= to_timestamp(%s/1000.0) AND timestamp < to_timestamp(%s/1000.0)""",
                    (alias, a, b))
                row = cur.fetchone()
                reports[d] = row[0] if row else 0
                cur.execute("""SELECT s->>'StateEnum', s->>'MachineHandle', s->'UnixMsList', s->'StateList'
                    FROM gridworks.messages m, jsonb_array_elements(m.payload->'Report'->'StateList') s
                    WHERE from_alias=%s AND message_type_name='report.event'
                      AND timestamp >= to_timestamp(%s/1000.0) AND timestamp < to_timestamp(%s/1000.0)
                      AND s->>'StateEnum' = ANY(%s)""", (alias, a, b, list(ENUMS)))
                for se, mh, ts, vs in cur.fetchall():
                    series.setdefault((se, mh), []).extend(zip(ts, vs))
            reb, flat = Counter(), Counter()
            for (se, mh), pts in series.items():
                cps = collapse(pts)
                target = "RelayOpening" if se == "pico.cycler.state" else "Flatlined"
                for i, (t, v) in enumerate(cps):
                    if i == 0 or v != target:
                        continue  # first point has no known predecessor
                    d = datetime.datetime.fromtimestamp(t / 1000, tz=ET).date()
                    if se == "pico.cycler.state":
                        reb[d] += 1
                    else:
                        flat[(d, mh)] += 1
            handles = sorted({mh for (se, mh) in series if se == "single.pico.state"})
            for d in days:
                reb_rows.append((d.isoformat(), house, reb[d]))
                rep_rows.append((d.isoformat(), house, reports[d]))
                for mh in handles:
                    flat_rows.append((d.isoformat(), house, mh, flat[(d, mh)]))
            print(house, "reboots", sum(reb.values()), "pico handles", len(handles),
                  "zero-report days", [d.isoformat()[5:] for d in days if reports[d] == 0], flush=True)
    for name, hdr, rows in [
        ("reboots-by-house-day.csv", ("date", "house", "bus_reboots"), reb_rows),
        ("flatlines-by-pico-day.csv", ("date", "house", "machine_handle", "flatlines"), flat_rows),
        ("reports-by-house-day.csv", ("date", "house", "report_events"), rep_rows),
    ]:
        with open(OUT / name, "w", newline="") as f:
            w = csv.writer(f); w.writerow(hdr); w.writerows(rows)

if __name__ == "__main__":
    main()
