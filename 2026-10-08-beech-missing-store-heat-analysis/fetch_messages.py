"""Pull beech's own messages for the night of 2026-01-04/05 from the journal DB.

Writes one gzipped JSON-lines file per message type into ./evidence/, each
line the untouched journal payload:

- report.event      — StateList (every state machine) + ChannelReadingList
- heating.forecast  — the scada's hourly forecast, RswtF and RswtDeltaTF
- layout.lite       — the scada's layout at its restarts, carrying Ha1Params

The window is wider than the night for layout.lite, which the scada sends
only at boot: the last boot before the night (2026-01-02) holds the
parameters that ran it.

    uv run python fetch_messages.py
"""

import gzip
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from spot_check import db_url, et_ms  # noqa: E402

SCADA = "hw1.isone.me.versant.keene.beech.scada"
OUT = Path(__file__).resolve().parent / "evidence"

WINDOWS = {
    "report.event": ("2026-01-04 18:00", "2026-01-05 10:00"),
    "heating.forecast": ("2026-01-04 18:00", "2026-01-05 10:00"),
    "layout.lite": ("2026-01-02 00:00", "2026-01-05 14:00"),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with psycopg.connect(db_url()) as conn:
        conn.read_only = True
        for type_name, (start, end) in WINDOWS.items():
            rows = conn.execute(
                """SELECT payload FROM gridworks.messages
                   WHERE from_alias = %s AND message_type_name = %s
                     AND timestamp >= to_timestamp(%s / 1000.0)
                     AND timestamp <  to_timestamp(%s / 1000.0)
                   ORDER BY timestamp""",
                (SCADA, type_name, et_ms(start), et_ms(end)),
            ).fetchall()
            path = OUT / f"beech.scada-{type_name}.jsonl.gz"
            with gzip.open(path, "wt") as f:
                for (payload,) in rows:
                    f.write(json.dumps(payload) + "\n")
            print(f"wrote {path.name} ({len(rows)} messages)")


if __name__ == "__main__":
    main()
