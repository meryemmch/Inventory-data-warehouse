"""Extract: read the raw CSV files and fail early if their structure is wrong."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.config import RAW_DIR

log = logging.getLogger(__name__)

RAW_FILES = {
    "stores": "stores.csv",
    "products": "products.csv",
    "inventory": "inventory_snapshots.csv",
}

REQUIRED_COLUMNS = {
    "stores": {"Store_ID", "Opening_Date", "City", "State", "Store_Address", "Zip_Code"},
    "products": {
        "Product_ID", "Product_Name", "Category", "Subcategory", "Brand", "Price", "Competitor_Pricing",
    },
    "inventory": {
        "Date", "Store_ID", "Product_ID", "Category", "Subcategory", "Inventory_Level",
        "Units_Sold", "Units_Ordered", "Demand_Forecast", "Price", "Holiday_Promotion",
        "Competitor_Pricing", "Brand",
    },
}


class SchemaError(ValueError):
    """Raised when a raw file does not have the expected columns."""


def read_raw(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for name, filename in RAW_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing raw file: {path}")
        df = pd.read_csv(path, dtype={"Zip_Code": "string"})
        missing = REQUIRED_COLUMNS[name] - set(df.columns)
        if missing:
            raise SchemaError(f"{filename} is missing columns: {sorted(missing)}")
        log.info("Extracted %-10s %6d rows from %s", name, len(df), filename)
        frames[name] = df
    return frames
