from __future__ import annotations

import os
from pathlib import Path

try: 
    from dotenv import load_dotenv

    load_dotenv()
except ImportError: 
    pass

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SQL_DIR = ROOT / "sql"
DOCS_IMG_DIR = ROOT / "docs" / "img"
DEFAULT_SQLITE_PATH = ROOT / "warehouse" / "inventory_dwh.db"

SEED = int(os.getenv("PIPELINE_SEED", "42"))


def get_database_url() -> str:
    """Return the SQLAlchemy URL. Credentials come from the environment, never from code."""
    return os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}")


# Fixed-date Indian public holidays used to flag dim_date.is_holiday.
# Movable festivals (Diwali, Holi, Eid...) are intentionally not included.
FIXED_HOLIDAYS: dict[tuple[int, int], str] = {
    (1, 26): "Republic Day",
    (8, 15): "Independence Day",
    (10, 2): "Gandhi Jayanti",
    (12, 25): "Christmas Day",
}


HOME_APPLIANCE_BRANDS = [
    "HomePro", "KitchenCraft", "ApplianceHub", "DomesticEdge", "LivingEase", "SweetHome",
]
PLACEHOLDER_BRAND = "GenericBrand"
