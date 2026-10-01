"""Database helpers: engine creation and schema management."""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url

from src.config import SQL_DIR, get_database_url


def get_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url)

    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless asked to enforce them.
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def split_sql_statements(sql: str) -> list[str]:
    """Split a .sql file into individual statements (comments removed)."""
    no_comments = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def create_schema(engine: Engine, schema_path: Path = SQL_DIR / "schema.sql") -> None:
    """Drop and recreate all warehouse tables from sql/schema.sql (full refresh)."""
    statements = split_sql_statements(schema_path.read_text(encoding="utf-8"))
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
