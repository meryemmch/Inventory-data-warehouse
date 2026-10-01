"""Data-quality checks. Critical failures stop the pipeline; warnings are only reported."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

log = logging.getLogger(__name__)


class DataQualityError(RuntimeError):
    """Raised when at least one critical check fails."""


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    critical: bool = True


def _result(name: str, passed: bool, detail: str, critical: bool = True) -> CheckResult:
    return CheckResult(name=name, passed=bool(passed), detail=detail, critical=critical)


def run_pre_load_checks(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    store, product, date, fact = t["dim_store"], t["dim_product"], t["dim_date"], t["fact_inventory"]
    measures = ["inventory_level", "units_sold", "units_ordered", "demand_forecast"]
    results: list[CheckResult] = []

    # --- keys and uniqueness
    for name, df, key in [
        ("dim_store.store_id", store, "store_id"),
        ("dim_product.product_id", product, "product_id"),
        ("dim_date.date_id", date, "date_id"),
        ("fact_inventory.inventory_fact_id", fact, "inventory_fact_id"),
    ]:
        dups = int(df[key].duplicated().sum())
        results.append(_result(f"unique_key:{name}", dups == 0, f"{dups} duplicate keys"))

    grain_dups = int(fact.duplicated(["date_id", "store_id", "product_id"]).sum())
    results.append(_result("fact_grain_unique", grain_dups == 0, f"{grain_dups} duplicate date/store/product rows"))

    # --- no nulls
    for name, df in t.items():
        required = [c for c in df.columns if not (name == "dim_date" and c == "holiday_name")]
        nulls = int(df[required].isna().sum().sum())
        results.append(_result(f"no_nulls:{name}", nulls == 0, f"{nulls} null values"))

    # --- referential integrity (fact -> dimensions)
    for fk, dim, key in [("store_id", store, "store_id"), ("product_id", product, "product_id"),
                         ("date_id", date, "date_id")]:
        orphans = int((~fact[fk].isin(dim[key])).sum())
        results.append(_result(f"fk_coverage:{fk}", orphans == 0, f"{orphans} fact rows without a matching dimension row"))

    # --- value rules
    negatives = int((fact[measures] < 0).sum().sum())
    results.append(_result("measures_non_negative", negatives == 0, f"{negatives} negative values"))
    bad_price = int((fact["unit_price"] <= 0).sum() + (fact["competitor_price"] <= 0).sum())
    results.append(_result("prices_positive", bad_price == 0, f"{bad_price} non-positive prices"))
    revenue_gap = float((fact["revenue"] - fact["units_sold"] * fact["unit_price"]).abs().max())
    results.append(_result("revenue_matches_units_x_price", revenue_gap <= 0.01, f"max gap {revenue_gap:.4f}"))

    # --- business rule: no sales before the store opened
    opening = store.set_index("store_id")["opening_date"]
    fact_dates = fact["date_id"].map(date.set_index("date_id")["full_date"])
    before_opening = int((fact_dates < fact["store_id"].map(opening)).sum())
    results.append(_result("no_sales_before_store_opening", before_opening == 0, f"{before_opening} rows"))

    # --- warnings (reported, never fatal)
    over = float((fact["units_sold"] > fact["inventory_level"]).mean() * 100)
    results.append(_result("units_sold_exceeds_inventory", True,
                           f"{over:.1f}% of rows sold more than the recorded inventory level", critical=False))
    idle_stores = sorted(set(store["store_id"]) - set(fact["store_id"]))
    results.append(_result("stores_without_activity", True,
                           f"{len(idle_stores)} stores have no fact rows: {idle_stores}", critical=False))
    idle_products = int((~product["product_id"].isin(fact["product_id"])).sum())
    results.append(_result("products_without_activity", True,
                           f"{idle_products} products have no fact rows", critical=False))
    return results


def run_post_load_checks(engine: Engine, expected_rows: dict[str, int]) -> list[CheckResult]:
    results: list[CheckResult] = []
    with engine.connect() as conn:
        for table, expected in expected_rows.items():
            actual = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            results.append(_result(f"row_count:{table}", actual == expected, f"expected {expected}, found {actual}"))
        for dim, key in [("dim_store", "store_id"), ("dim_product", "product_id"), ("dim_date", "date_id")]:
            orphans = conn.execute(
                text(f"SELECT COUNT(*) FROM fact_inventory f LEFT JOIN {dim} d ON d.{key} = f.{key} WHERE d.{key} IS NULL")
            ).scalar_one()
            results.append(_result(f"db_orphans:{dim}", orphans == 0, f"{orphans} orphan fact rows"))
    return results


def enforce(results: list[CheckResult]) -> None:
    for r in results:
        level = logging.INFO if r.passed else (logging.ERROR if r.critical else logging.WARNING)
        log.log(level, "%-4s %-36s %s", "OK" if r.passed else "FAIL", r.name, r.detail)
    failed = [r for r in results if r.critical and not r.passed]
    if failed:
        raise DataQualityError("Critical data-quality checks failed: " + ", ".join(r.name for r in failed))


def write_report(results: list[CheckResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
