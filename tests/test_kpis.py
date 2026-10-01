import pytest

from src.kpis import load_queries, run_kpi


def test_every_kpi_query_runs_and_returns_rows(warehouse):
    engine, _ = warehouse
    names = list(load_queries())
    assert len(names) >= 15
    for name in names:
        df = run_kpi(engine, name)
        assert len(df) > 0, f"{name} returned no rows"


def test_turnover_and_dsi_are_consistent(warehouse):
    engine, _ = warehouse
    row = run_kpi(engine, "kpi_overview").iloc[0]
    assert row["annualized_turnover"] * row["days_sales_of_inventory"] == pytest.approx(365, rel=0.01)
    assert 0 <= row["stock_out_rate_pct"] <= 100
    assert 0 <= row["excess_inventory_pct"] <= 100


def test_category_revenue_shares_sum_to_100(warehouse):
    engine, _ = warehouse
    shares = run_kpi(engine, "revenue_by_category")["revenue_share_pct"].sum()
    assert shares == pytest.approx(100, abs=0.1)


def test_category_revenue_adds_up_to_total(warehouse):
    engine, _ = warehouse
    total = run_kpi(engine, "kpi_overview").iloc[0]["revenue"]
    assert run_kpi(engine, "revenue_by_category")["revenue"].sum() == pytest.approx(total, rel=1e-6)


def test_abc_classes_partition_all_sold_products(warehouse):
    engine, _ = warehouse
    summary = run_kpi(engine, "abc_summary")
    assert set(summary["abc_class"]) == {"A", "B", "C"}
    assert summary["revenue_share_pct"].sum() == pytest.approx(100, abs=0.1)
    assert summary["products"].sum() == len(run_kpi(engine, "abc_analysis"))


def test_monthly_growth_is_chronological_and_first_month_has_no_growth(warehouse):
    engine, _ = warehouse
    monthly = run_kpi(engine, "monthly_revenue_growth")
    assert monthly["mom_growth_pct"].isna().iloc[0]
    ordered = monthly.sort_values(["year", "month"]).reset_index(drop=True)
    assert ordered.equals(monthly)


def test_store_performance_lists_stores_without_activity(warehouse):
    engine, _ = warehouse
    stores = run_kpi(engine, "store_performance")
    assert len(stores) == 10
    assert (stores.loc[stores["snapshots"] == 0, "revenue"] == 0).all()
