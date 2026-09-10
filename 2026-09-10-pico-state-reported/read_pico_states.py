"""The latest pico-state rows for spruce from the production journal,
decoded with the journalkeeper's own enum: the journal stores a state as
the value's index in the enum word's value list (report_event_persistor
get_sema_enum_value), so the same list turns it back into the name.

Run from the journalkeeper checkout, whose env has the vendored enum:
    cd gridworks-journalkeeper && uv run python ../experiments/2026-09-10-pico-state-reported/read_pico_states.py [N]
GJK_DB_URL comes from experiments/.env.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from gjk.sema.enums import SinglePicoState
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
ta = "hw1.isone.me.versant.keene.spruce.ta"
query = text("""
    select r.timestamp at time zone 'UTC' as utc, c.name, r.value
    from gridworks.readings r
    join gridworks.reading_channels c on c.id = r.channel_id
    where c.terminal_asset_alias = :ta
      and c.unit_type = :unit_type
      and r.timestamp > now() - interval '8 hours'
    order by r.timestamp desc, c.name
    limit :n
""")
with create_engine(os.environ["GJK_DB_URL"]).connect() as conn:
    rows = conn.execute(
        query, {"ta": ta, "unit_type": SinglePicoState.enum_name(), "n": n}
    ).all()
for utc, name, value in reversed(rows):
    print(f"{utc:%H:%M:%S}  {name:28s} {value}  {SinglePicoState.values()[int(value)]}")
