#!/usr/bin/env python3
"""Archive the spruce scada's glitch messages for the blackout window
(READ-ONLY against the analytics DB).

Pulls every glitch the spruce scada emitted 2026-08-10 16:00-23:00 ET,
decodes each through the vendored `glitch` word, and writes one instance
file per glitch under `instances/`, named per the eventstore key grammar
`<subject>-<condition>-glitch-000.json` with subject
`<node dashes-to-dots>.<created-ms>` and condition `pico.blackout`.
The glitches live in the immutable store (gridworks.messages); this
archive makes the incident's subset citable from the folder with no DB
access.

Run with GJK_DB_URL in experiments/.env:
  uv run python archive_glitches.py
"""

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from pydantic import TypeAdapter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import LeftRightDot  # noqa: E402
from gwexp.sema.types import Glitch  # noqa: E402

ET = ZoneInfo("America/New_York")
_LRD = TypeAdapter(LeftRightDot)

SPRUCE_SCADA_TAIL = ".spruce.scada"
WINDOW_START_ET = datetime(2026, 8, 10, 16, 0, tzinfo=ET)
WINDOW_END_ET = datetime(2026, 8, 10, 23, 0, tzinfo=ET)
CONDITION: LeftRightDot = _LRD.validate_python("pico.blackout")


def db_url() -> str:
    for line in (HERE.parent / ".env").read_text().splitlines():
        if line.startswith("GJK_DB_URL="):
            return line.split("=", 1)[1].strip().strip("'\"").replace(
                "postgresql+psycopg://", "postgresql://")
    raise SystemExit("GJK_DB_URL not found in experiments/.env")


def instance_filename(g: Glitch) -> str:
    """Eventstore key grammar: subject-condition-typename-version, each
    field internally LeftRightDot; the spaceheat node's dashes become
    dots and the created-ms stamp keeps repeat emitters distinct."""
    subject = _LRD.validate_python(
        f"{g.node.replace('-', '.')}.{g.created_ms}")
    return f"{subject}-{CONDITION}-glitch-000.json"


def main() -> int:
    codec = SemaCodec()
    out_dir = HERE / "instances" / CONDITION
    out_dir.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(db_url()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.payload
                FROM gridworks.messages m
                WHERE m.message_type_name = 'glitch'
                  AND m.timestamp >= %s AND m.timestamp < %s
                ORDER BY m.timestamp
                """,
                (WINDOW_START_ET, WINDOW_END_ET),
            )
            glitches = [codec.from_dict(payload, expect=Glitch)
                        for (payload,) in cur.fetchall()]

    spruce = [g for g in glitches
              if g.from_g_node_alias.endswith(SPRUCE_SCADA_TAIL)]
    by_summary: Counter[str] = Counter()
    for g in spruce:
        (out_dir / instance_filename(g)).write_text(
            json.dumps(g.to_dict(), indent=2) + "\n")
        by_summary[g.summary] += 1
        created = datetime.fromtimestamp(g.created_ms / 1000, tz=ET)
        print(f"{created.strftime('%H:%M:%S')}  {g.summary:20} "
              f"node={g.node}")
    print(f"\n{len(spruce)} spruce glitches archived to {out_dir}/ "
          f"({len(glitches)} fleet-wide in window): "
          + "  ".join(f"{s}x{n}" for s, n in by_summary.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
