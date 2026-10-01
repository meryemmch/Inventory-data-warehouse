"""Load: create the schema, insert the tables, and export CSVs for BI tools."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine

from src.db import create_schema

log = logging.getLogger(__name__)

# Dimensions first, fact last (foreign keys point from fact to dimensions).
LOAD_ORDER = ["dim_store", "dim_product", "dim_date", "fact_inventory"]


def load_warehouse(engine: Engine, tables: dict[str, pd.DataFrame]) -> None:
    """Full refresh: recreate the schema, then load every table in one transaction."""
    create_schema(engine)
    with engine.begin() as conn:
        for name in LOAD_ORDER:
            tables[name].to_sql(name, conn, if_exists="append", index=False, chunksize=1000)
            log.info("Loaded %-15s %6d rows", name, len(tables[name]))


def export_csv(tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    """Write the final tables as CSV so Power BI / Tableau / Excel can import them directly."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    log.info("Exported %d CSV files to %s", len(tables), out_dir)
