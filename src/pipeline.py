"""End-to-end ETL: extract -> transform -> quality checks -> load -> verify.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src import config
from src.db import get_engine
from src.extract import read_raw
from src.load import export_csv, load_warehouse
from src.quality import enforce, run_post_load_checks, run_pre_load_checks, write_report
from src.transform import transform

log = logging.getLogger("pipeline")


def run(
    database_url: str | None = None,
    raw_dir: Path = config.RAW_DIR,
    processed_dir: Path | None = config.PROCESSED_DIR,
    seed: int = config.SEED,
) -> dict[str, int]:
    """Run the full pipeline and return the row count of each loaded table."""
    raw = read_raw(raw_dir)
    tables = transform(raw, seed)

    pre = run_pre_load_checks(tables)
    enforce(pre)  # stops here if a critical check fails - nothing is loaded

    engine = get_engine(database_url)
    load_warehouse(engine, tables)

    counts = {name: len(df) for name, df in tables.items()}
    post = run_post_load_checks(engine, counts)
    enforce(post)

    if processed_dir is not None:
        export_csv(tables, processed_dir)
        write_report(pre + post, processed_dir / "dq_report.json")
    engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the inventory data warehouse.")
    parser.add_argument("--database-url", help="SQLAlchemy URL (default: DATABASE_URL env var or local SQLite)")
    parser.add_argument("--seed", type=int, default=config.SEED, help="seed for the product mapping")
    parser.add_argument("--no-export", action="store_true", help="skip writing CSV exports")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    counts = run(
        database_url=args.database_url,
        processed_dir=None if args.no_export else config.PROCESSED_DIR,
        seed=args.seed,
    )
    log.info("Pipeline finished: %s", counts)


if __name__ == "__main__":
    main()
