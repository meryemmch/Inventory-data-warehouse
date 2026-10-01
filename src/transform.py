"""Transform: clean the raw data and shape it into star-schema tables.

Every function is pure (DataFrame in, DataFrame out) so it can be unit-tested.
"""
from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
import pandas as pd

from src.config import FIXED_HOLIDAYS, HOME_APPLIANCE_BRANDS, PLACEHOLDER_BRAND

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- dimensions
def clean_stores(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(
        columns={
            "Store_ID": "store_id", "City": "city", "State": "state",
            "Store_Address": "address", "Zip_Code": "postal_code", "Opening_Date": "opening_date",
        }
    ).copy()
    # Some addresses contain a literal "\n" (from the Faker generator) - turn it into ", ".
    df["address"] = (
        df["address"].str.replace(r"\\n|\n", ", ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    )
    for col in ("city", "state", "postal_code"):
        df[col] = df[col].astype("string").str.strip()
    df["opening_date"] = pd.to_datetime(df["opening_date"]).dt.strftime("%Y-%m-%d")
    df["store_id"] = df["store_id"].astype("int64")
    return df[["store_id", "city", "state", "address", "postal_code", "opening_date"]].drop_duplicates()


def clean_products(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    df = raw.rename(
        columns={
            "Product_ID": "product_id", "Product_Name": "product_name", "Category": "category",
            "Subcategory": "subcategory", "Brand": "brand", "Price": "list_price",
            "Competitor_Pricing": "competitor_list_price",
        }
    ).copy()
    for col in ("product_name", "category", "subcategory", "brand"):
        df[col] = df[col].astype("string").str.strip()

    # Fix: Home Appliances were left with the placeholder brand (typo in the v1 lookup).
    mask = (df["brand"] == PLACEHOLDER_BRAND) & (df["category"] == "Home Appliances")
    if mask.any():
        df.loc[mask, "brand"] = rng.choice(HOME_APPLIANCE_BRANDS, size=int(mask.sum()))
        log.info("Replaced placeholder brand on %d Home Appliances products", int(mask.sum()))

    df["product_id"] = df["product_id"].astype("int64")
    df["list_price"] = df["list_price"].round(2)
    df["competitor_list_price"] = df["competitor_list_price"].round(2)
    return df.drop_duplicates(subset="product_id")


def build_dim_date(min_date: pd.Timestamp, max_date: pd.Timestamp) -> pd.DataFrame:
    """A complete calendar from Jan 1 of the first year to Dec 31 of the last year."""
    days = pd.date_range(f"{min_date.year}-01-01", f"{max_date.year}-12-31", freq="D")
    iso = days.isocalendar()
    holiday_names = [FIXED_HOLIDAYS.get((d.month, d.day)) for d in days]
    return pd.DataFrame(
        {
            "date_id": days.year * 10000 + days.month * 100 + days.day,
            "full_date": days.strftime("%Y-%m-%d"),
            "year": days.year,
            "quarter": days.quarter,
            "month": days.month,
            "month_name": days.month_name(),
            "iso_year": iso["year"].to_numpy(),
            "iso_week": iso["week"].to_numpy(),
            "day_of_month": days.day,
            "day_of_week": days.dayofweek + 1,
            "day_name": days.day_name(),
            "is_weekend": (days.dayofweek >= 5).astype(int),
            "is_holiday": [int(h is not None) for h in holiday_names],
            "holiday_name": holiday_names,
        }
    )


# --------------------------------------------------------------------------- fact table
def prepare_inventory(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardise column names/types and drop unusable rows (logged, never silent)."""
    df = raw.rename(
        columns={
            "Date": "date", "Store_ID": "store_id", "Category": "category", "Subcategory": "subcategory",
            "Inventory_Level": "inventory_level", "Units_Sold": "units_sold",
            "Units_Ordered": "units_ordered", "Demand_Forecast": "demand_forecast",
            "Holiday_Promotion": "is_promotion",
        }
    ).copy()
    before = len(df)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    measures = ["inventory_level", "units_sold", "units_ordered", "demand_forecast"]
    df = df.dropna(subset=["date", "store_id", "category", "subcategory", *measures])
    df = df[(df[measures] >= 0).all(axis=1)].drop_duplicates()
    if len(df) != before:
        log.warning("Dropped %d unusable inventory rows", before - len(df))
    df["is_promotion"] = df["is_promotion"].astype(bool).astype(int)
    for col in ["store_id", *measures]:
        df[col] = df[col].astype("int64")
    return df.drop(columns=["Product_ID", "Price", "Competitor_Pricing", "Brand"], errors="ignore").reset_index(
        drop=True
    )


def assign_products(inventory: pd.DataFrame, products: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """Give every inventory row a valid product_id from the product dimension.

    The raw inventory file has no usable product key (its Product_ID is just a row counter
    from 0 to n-1 and 92% of those values do not exist in the product table). Instead of
    joining by row position (the v1 bug), each row is mapped - reproducibly, via a seeded RNG -
    to a product of the SAME category and subcategory. A product is never used twice for the
    same store on the same day, so the fact table's grain stays unique.
    """
    pools = {key: grp["product_id"].to_numpy() for key, grp in products.groupby(["category", "subcategory"])}
    used: dict[tuple, set[int]] = defaultdict(set)
    assigned: list[int] = []
    for row in inventory.itertuples(index=False):
        pool = pools.get((row.category, row.subcategory))
        if pool is None:
            raise ValueError(f"No products for category/subcategory {row.category}/{row.subcategory}")
        taken = used[(row.date, row.store_id)]
        candidates = [p for p in pool if p not in taken]
        if not candidates:
            raise ValueError("Product pool exhausted for one store/day; cannot keep the grain unique")
        pid = int(rng.choice(candidates))
        taken.add(pid)
        assigned.append(pid)
    return pd.Series(assigned, index=inventory.index, name="product_id")


def build_fact(inventory: pd.DataFrame, products: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    df = inventory.copy()
    df["product_id"] = assign_products(df, products, rng)
    df = df.merge(
        products[["product_id", "list_price", "competitor_list_price"]], on="product_id", how="left", validate="m:1"
    )
    df["unit_price"] = df["list_price"]
    df["competitor_price"] = df["competitor_list_price"]
    df["revenue"] = (df["units_sold"] * df["unit_price"]).round(2)
    df["date_id"] = df["date"].dt.year * 10000 + df["date"].dt.month * 100 + df["date"].dt.day
    df = df.sort_values(["date_id", "store_id", "product_id"]).reset_index(drop=True)
    df["inventory_fact_id"] = np.arange(1, len(df) + 1)
    return df[
        [
            "inventory_fact_id", "date_id", "store_id", "product_id", "inventory_level", "units_sold",
            "units_ordered", "demand_forecast", "unit_price", "competitor_price", "revenue", "is_promotion",
        ]
    ]


def transform(raw: dict[str, pd.DataFrame], seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dim_store = clean_stores(raw["stores"])
    dim_product = clean_products(raw["products"], rng)
    inventory = prepare_inventory(raw["inventory"])
    fact = build_fact(inventory, dim_product, rng)
    dim_date = build_dim_date(inventory["date"].min(), inventory["date"].max())
    log.info(
        "Transformed: dim_store=%d dim_product=%d dim_date=%d fact_inventory=%d",
        len(dim_store), len(dim_product), len(dim_date), len(fact),
    )
    return {"dim_store": dim_store, "dim_product": dim_product, "dim_date": dim_date, "fact_inventory": fact}
