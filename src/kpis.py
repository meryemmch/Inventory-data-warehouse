"""Run the named KPI queries stored in sql/kpi_queries.sql."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from src.config import SQL_DIR

NAME_MARKER = "-- name:"


def load_queries(path: Path = SQL_DIR / "kpi_queries.sql") -> dict[str, str]:
    queries: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(NAME_MARKER):
            current = line[len(NAME_MARKER):].strip()
            queries[current] = []
        elif current is not None:
            queries[current].append(line)
    return {name: "\n".join(lines).strip().rstrip(";") for name, lines in queries.items()}


def run_kpi(engine: Engine, name: str) -> pd.DataFrame:
    queries = load_queries()
    if name not in queries:
        raise KeyError(f"Unknown KPI query '{name}'. Available: {sorted(queries)}")
    with engine.connect() as conn:
        return pd.read_sql(text(queries[name]), conn)
