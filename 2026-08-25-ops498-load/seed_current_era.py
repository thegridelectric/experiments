"""Copy prod's current channel state into the dev DB.

Every `reading_channels` row (active and retired) and, per house, the newest
`layout.lite` messages row — the two things the layout sync guard and the
era lookup compare against. Prod is read through the read-only visualizer
URL (`GJK_DB_URL` in experiments/.env); dev through `DEV_DB_URL`.
"""

import os

from gw_data.db.models import MessageSql, ReadingChannelSql
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

PROD_URL = os.environ["GJK_DB_URL"]
DEV_URL = os.environ["DEV_DB_URL"]
LAYOUT_LITE = "layout.lite"


def copy_row(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def main() -> None:
    prod = create_engine(PROD_URL)
    dev = create_engine(DEV_URL)
    with Session(prod) as src, Session(dev) as dst:
        channels = src.scalars(select(ReadingChannelSql)).all()
        newest = (
            select(MessageSql.from_alias, func.max(MessageSql.timestamp).label("ts"))
            .where(MessageSql.message_type_name == LAYOUT_LITE)
            .group_by(MessageSql.from_alias)
            .subquery()
        )
        layouts = src.scalars(
            select(MessageSql).join(
                newest,
                (MessageSql.from_alias == newest.c.from_alias)
                & (MessageSql.timestamp == newest.c.ts),
            )
        ).all()
        dst.bulk_insert_mappings(ReadingChannelSql, [copy_row(c) for c in channels])
        dst.bulk_insert_mappings(MessageSql, [copy_row(m) for m in layouts])
        dst.commit()
        print(f"seeded {len(channels)} reading_channels rows, {len(layouts)} newest layouts")
        for m in layouts:
            print(f"  {m.from_alias} {m.timestamp.isoformat()}")


if __name__ == "__main__":
    main()
