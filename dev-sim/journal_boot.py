"""Create the local journal roles and tables, then start the keeper.

The timescale container comes up empty. Roles follow the dev convention
(password equals the role name). Tables are the gw_data models installed
in the keeper image.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from sqlalchemy import create_engine, text

HOUSE_DIRS = (Path("/house"), Path("/house-buffer"))

ADMIN_URL = os.environ["JOURNAL_ADMIN_URL"]
ROLES = (
    "gw_admin",
    "gw_journalkeeper",
    "gw_visualizer",
    "gw_alerts",
    "gw_analyst",
)
STATEMENT_TIMEOUT = {
    "gw_journalkeeper": "10s",
    "gw_visualizer": "10s",
    "gw_alerts": "2min",
    "gw_analyst": "2min",
}


def _wait_for_db() -> None:
    deadline = time.monotonic() + 180
    while True:
        engine = None
        try:
            socket.create_connection(("127.0.0.1", 5432), 1).close()
            engine = create_engine(ADMIN_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return
        except Exception:
            if engine is not None:
                engine.dispose()
            engine = None
            if time.monotonic() > deadline:
                raise SystemExit("journal database still closed")
            time.sleep(1)


def _bootstrap() -> None:
    import gw_data.db.models  # noqa: F401
    from gw_data.db.models._base import Base

    engine = create_engine(ADMIN_URL)
    with engine.begin() as conn:
        for name in ROLES:
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
                {"name": name},
            ).first()
            if exists is None:
                conn.execute(text(f"CREATE USER {name} PASSWORD '{name}'"))
        conn.execute(text("REVOKE CONNECT ON DATABASE tsdb FROM PUBLIC"))
        conn.execute(text("GRANT ALL ON DATABASE tsdb TO gw_admin"))
        for name in ROLES:
            if name != "gw_admin":
                conn.execute(text(f"GRANT CONNECT ON DATABASE tsdb TO {name}"))
        for name, timeout in STATEMENT_TIMEOUT.items():
            conn.execute(
                text(f"ALTER ROLE {name} SET statement_timeout = '{timeout}'")
            )
        conn.execute(
            text(
                "ALTER DATABASE tsdb SET idle_in_transaction_session_timeout = '5min'"
            )
        )
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gridworks"))
        for name in ("gw_journalkeeper", "gw_visualizer", "gw_alerts", "gw_analyst"):
            conn.execute(text(f"GRANT USAGE ON SCHEMA gridworks TO {name}"))
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA gridworks "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gw_journalkeeper"
            )
        )
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA gridworks "
                "GRANT ALL PRIVILEGES ON SEQUENCES TO gw_journalkeeper"
            )
        )
        for name in ("gw_visualizer", "gw_alerts", "gw_analyst"):
            conn.execute(
                text(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA gridworks "
                    f"GRANT SELECT ON TABLES TO {name}"
                )
            )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON ALL TABLES IN SCHEMA gridworks TO gw_journalkeeper"
            )
        )
        conn.execute(
            text(
                "GRANT ALL PRIVILEGES ON ALL SEQUENCES "
                "IN SCHEMA gridworks TO gw_journalkeeper"
            )
        )
        for name in ("gw_visualizer", "gw_alerts", "gw_analyst"):
            conn.execute(
                text(f"GRANT SELECT ON ALL TABLES IN SCHEMA gridworks TO {name}")
            )
        conn.execute(text("GRANT UPDATE ON gridworks.users TO gw_visualizer"))
        for folder in HOUSE_DIRS:
            layout_path = folder / "hardware-layout.json"
            if not layout_path.exists():
                continue
            layout = json.loads(layout_path.read_text())
            for g_node in layout["GNodes"]:
                if g_node.get("GNodeClass") != "TerminalAsset":
                    continue
                conn.execute(
                    text(
                        """
                        INSERT INTO gridworks.g_nodes
                            (id, alias, base_class, g_node_class, status, display_name)
                        VALUES (
                            :id, :alias, :base_class, :g_node_class, :status,
                            :display_name
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            alias = EXCLUDED.alias,
                            display_name = EXCLUDED.display_name,
                            status = EXCLUDED.status
                        """
                    ),
                    {
                        "id": g_node["GNodeId"],
                        "alias": g_node["Alias"],
                        "base_class": g_node["BaseClass"],
                        "g_node_class": g_node["GNodeClass"],
                        "status": g_node["Status"],
                        "display_name": g_node["DisplayName"],
                    },
                )
        conn.execute(
            text(
                """
                INSERT INTO gridworks.users (id, username, hashed_password, is_active)
                VALUES (
                    'b1eec000-0000-4000-8000-000000000001',
                    'beech',
                    crypt('beech', gen_salt('bf')),
                    true
                )
                ON CONFLICT (username) DO NOTHING
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO gridworks.user_installation_roles
                    (user_id, role, ta_g_node_id)
                SELECT 'b1eec000-0000-4000-8000-000000000001', 'admin', NULL
                WHERE NOT EXISTS (
                    SELECT 1 FROM gridworks.user_installation_roles
                    WHERE user_id = 'b1eec000-0000-4000-8000-000000000001'
                      AND ta_g_node_id IS NULL
                )
                """
            )
        )
    engine.dispose()


def main() -> None:
    _wait_for_db()
    _bootstrap()
    os.chdir("/app")
    os.execvp("python", ["python", "run_journal_keeper.py"])


if __name__ == "__main__":
    main()
