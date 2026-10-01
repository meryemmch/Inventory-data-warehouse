import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from src import pipeline
from src.db import get_engine
from src.extract import read_raw
from src.quality import DataQualityError, enforce, run_pre_load_checks
from src.transform import (
    assign_products, build_dim_date, clean_products, clean_stores, prepare_inventory, transform,
)


@pytest.fixture(scope="module")
def raw():
    return read_raw()


@pytest.fixture(scope="module")
def tables(raw):
    return transform(raw, seed=42)


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


# ------------------------------------------------------------------ pipeline / load
def test_no_rows_lost_between_raw_and_fact(warehouse, raw):
    _, counts = warehouse
    assert counts["fact_inventory"] == len(raw["inventory"])


def test_units_sold_total_reconciles_with_raw(warehouse, raw):
    engine, _ = warehouse
    assert scalar(engine, "SELECT SUM(units_sold) FROM fact_inventory") == raw["inventory"]["Units_Sold"].sum()


def test_no_orphan_fact_rows(warehouse):
    engine, _ = warehouse
    for dim, key in [("dim_store", "store_id"), ("dim_product", "product_id"), ("dim_date", "date_id")]:
        sql = f"SELECT COUNT(*) FROM fact_inventory f LEFT JOIN {dim} d ON d.{key} = f.{key} WHERE d.{key} IS NULL"
        assert scalar(engine, sql) == 0


def test_database_enforces_foreign_keys(warehouse):
    engine, _ = warehouse
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO fact_inventory VALUES (999999, 20230101, 999, 1, 1, 1, 1, 1, 1.0, 1.0, 1.0, 0)"
            ))


def test_pipeline_is_idempotent(tmp_path):
    url = f"sqlite:///{(tmp_path / 'idem.db').as_posix()}"
    first = pipeline.run(database_url=url, processed_dir=None)
    second = pipeline.run(database_url=url, processed_dir=None)
    assert first == second
    assert scalar(get_engine(url), "SELECT COUNT(*) FROM fact_inventory") == first["fact_inventory"]


def test_pipeline_is_deterministic(raw):
    a = transform(raw, seed=42)["fact_inventory"]
    b = transform(raw, seed=42)["fact_inventory"]
    pd.testing.assert_frame_equal(a, b)
    c = transform(raw, seed=7)["fact_inventory"]
    assert not a["product_id"].equals(c["product_id"])


# ------------------------------------------------------------------ transform rules
def test_assigned_products_keep_category_and_subcategory(raw):
    rng = np.random.default_rng(42)
    products = clean_products(raw["products"], rng)
    inventory = prepare_inventory(raw["inventory"])
    ids = assign_products(inventory, products, rng)
    lookup = products.set_index("product_id")[["category", "subcategory"]]
    mapped = lookup.loc[ids.to_numpy()].reset_index(drop=True)
    assert (mapped["category"].to_numpy() == inventory["category"].to_numpy()).all()
    assert (mapped["subcategory"].to_numpy() == inventory["subcategory"].to_numpy()).all()


def test_fact_grain_is_unique(tables):
    assert not tables["fact_inventory"].duplicated(["date_id", "store_id", "product_id"]).any()


def test_store_addresses_are_clean(tables):
    addresses = tables["dim_store"]["address"]
    assert not addresses.str.contains(r"\\n|\n", regex=True).any()


def test_placeholder_brand_is_gone(tables):
    assert "GenericBrand" not in set(tables["dim_product"]["brand"])


def test_dim_date_is_a_complete_calendar():
    dim = build_dim_date(pd.Timestamp("2023-03-05"), pd.Timestamp("2024-06-01"))
    assert len(dim) == 365 + 366                         # all of 2023 and all of 2024 (leap year)
    assert dim["date_id"].is_unique
    assert dim.loc[dim["full_date"] == "2023-08-15", "is_holiday"].item() == 1
    assert dim.loc[dim["full_date"] == "2023-08-16", "is_holiday"].item() == 0
    assert dim.loc[dim["full_date"] == "2023-01-01", "iso_week"].item() == 52   # ISO week belongs to 2022
    assert dim.loc[dim["full_date"] == "2023-01-01", "is_weekend"].item() == 1  # a Sunday


def test_stores_cleaning_keeps_ids(raw):
    stores = clean_stores(raw["stores"])
    assert sorted(stores["store_id"]) == sorted(raw["stores"]["Store_ID"])


# ------------------------------------------------------------------ data quality gate
def test_quality_gate_blocks_bad_data(tables):
    broken = {k: v.copy() for k, v in tables.items()}
    broken["fact_inventory"].loc[0, "store_id"] = 999          # orphan foreign key
    broken["fact_inventory"].loc[1, "units_sold"] = -5         # impossible value
    with pytest.raises(DataQualityError) as err:
        enforce(run_pre_load_checks(broken))
    message = str(err.value)
    assert "fk_coverage:store_id" in message and "measures_non_negative" in message


def test_quality_gate_passes_good_data(tables):
    enforce(run_pre_load_checks(tables))
