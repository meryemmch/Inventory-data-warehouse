-- =====================================================================================
-- 1. Inventory health
-- =====================================================================================

-- name: kpi_overview
SELECT
    COUNT(*)                                                                         AS snapshots,
    SUM(units_sold)                                                                  AS units_sold,
    ROUND(SUM(revenue), 2)                                                           AS revenue,
    ROUND(AVG(inventory_level), 1)                                                   AS avg_inventory_level,
    ROUND(365.0 * AVG(units_sold) / NULLIF(AVG(inventory_level), 0), 2)              AS annualized_turnover,
    ROUND(1.0 * AVG(inventory_level) / NULLIF(AVG(units_sold), 0), 2)                AS days_sales_of_inventory,
    ROUND(100.0 * SUM(CASE WHEN inventory_level = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS stock_out_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN inventory_level > demand_forecast
                           THEN inventory_level - demand_forecast ELSE 0 END)
          / NULLIF(SUM(inventory_level), 0), 2)                                      AS excess_inventory_pct
FROM fact_inventory;

-- name: inventory_health_by_category
SELECT
    p.category,
    COUNT(*)                                                                         AS snapshots,
    ROUND(AVG(f.inventory_level), 1)                                                 AS avg_inventory_level,
    ROUND(365.0 * AVG(f.units_sold) / NULLIF(AVG(f.inventory_level), 0), 2)          AS annualized_turnover,
    ROUND(1.0 * AVG(f.inventory_level) / NULLIF(AVG(f.units_sold), 0), 2)            AS days_sales_of_inventory,
    ROUND(100.0 * SUM(CASE WHEN f.inventory_level = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS stock_out_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN f.inventory_level > f.demand_forecast
                           THEN f.inventory_level - f.demand_forecast ELSE 0 END)
          / NULLIF(SUM(f.inventory_level), 0), 2)                                    AS excess_inventory_pct
FROM fact_inventory f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.category
ORDER BY p.category;

-- name: store_performance
-- LEFT JOIN from the store dimension so stores without any activity are visible (zero revenue, NULL KPIs).
SELECT
    s.store_id,
    s.city,
    s.state,
    COUNT(f.inventory_fact_id)                                                       AS snapshots,
    COALESCE(ROUND(SUM(f.revenue), 2), 0)                                            AS revenue,
    ROUND(365.0 * AVG(f.units_sold) / NULLIF(AVG(f.inventory_level), 0), 2)          AS annualized_turnover,
    ROUND(1.0 * AVG(f.inventory_level) / NULLIF(AVG(f.units_sold), 0), 2)            AS days_sales_of_inventory,
    ROUND(100.0 * SUM(CASE WHEN f.inventory_level = 0 THEN 1 ELSE 0 END)
          / NULLIF(COUNT(f.inventory_fact_id), 0), 2)                                AS stock_out_rate_pct
FROM dim_store s
LEFT JOIN fact_inventory f ON f.store_id = s.store_id
GROUP BY s.store_id, s.city, s.state
ORDER BY s.store_id;

-- =====================================================================================
-- 2. Sales and demand
-- =====================================================================================

-- name: revenue_by_category
SELECT
    p.category,
    SUM(f.units_sold)                                                                AS units_sold,
    ROUND(SUM(f.revenue), 2)                                                         AS revenue,
    ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (), 2)                   AS revenue_share_pct
FROM fact_inventory f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.category
ORDER BY revenue DESC;

-- name: revenue_by_state
SELECT
    s.state,
    COUNT(*)                                                                         AS snapshots,
    ROUND(SUM(f.revenue), 2)                                                         AS revenue,
    ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (), 2)                   AS revenue_share_pct
FROM fact_inventory f
JOIN dim_store s ON s.store_id = f.store_id
GROUP BY s.state
ORDER BY revenue DESC;

-- name: forecast_error_by_category
-- Replaces v1's "accuracy" formula (a signed error, not an accuracy). WAPE is the standard error measure.
SELECT
    p.category,
    ROUND(100.0 * SUM(ABS(f.units_sold - f.demand_forecast)) / NULLIF(SUM(f.units_sold), 0), 2) AS forecast_wape_pct,
    ROUND(100.0 * (SUM(f.demand_forecast) - SUM(f.units_sold)) / NULLIF(SUM(f.units_sold), 0), 2) AS forecast_bias_pct
FROM fact_inventory f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.category
ORDER BY p.category;

-- name: monthly_revenue_growth
-- Month-over-month growth, ordered by (year, month) so it stays correct across years.
-- "snapshots" is shown because totals depend on how many daily snapshots exist in each month.
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        COUNT(*)            AS snapshots,
        SUM(f.units_sold)   AS units_sold,
        SUM(f.revenue)      AS revenue
    FROM fact_inventory f
    JOIN dim_date d ON d.date_id = f.date_id
    GROUP BY d.year, d.month
)
SELECT
    year,
    month,
    snapshots,
    units_sold,
    ROUND(revenue, 2)                                                                AS revenue,
    ROUND(revenue / snapshots, 2)                                                    AS revenue_per_snapshot,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY year, month))
          / NULLIF(LAG(revenue) OVER (ORDER BY year, month), 0), 2)                  AS mom_growth_pct
FROM monthly
ORDER BY year, month;

-- name: quarterly_revenue_yoy
-- Year-over-year growth: each quarter compared with the same quarter of the previous year.
WITH quarterly AS (
    SELECT d.year, d.quarter, COUNT(*) AS snapshots, SUM(f.revenue) AS revenue
    FROM fact_inventory f
    JOIN dim_date d ON d.date_id = f.date_id
    GROUP BY d.year, d.quarter
)
SELECT
    year,
    quarter,
    snapshots,
    ROUND(revenue, 2)                                                                AS revenue,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (PARTITION BY quarter ORDER BY year))
          / NULLIF(LAG(revenue) OVER (PARTITION BY quarter ORDER BY year), 0), 2)    AS yoy_growth_pct
FROM quarterly
ORDER BY year, quarter;

-- =====================================================================================
-- 3. Product performance
-- =====================================================================================

-- name: top_products
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.brand,
    COUNT(*)                                                                         AS snapshots,
    SUM(f.units_sold)                                                                AS units_sold,
    ROUND(SUM(f.revenue), 2)                                                         AS revenue,
    RANK() OVER (ORDER BY SUM(f.revenue) DESC)                                       AS revenue_rank
FROM fact_inventory f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.product_id, p.product_name, p.category, p.brand
ORDER BY revenue_rank
LIMIT 10;

-- name: abc_analysis
-- Pareto classification: A = products making up the first 80% of revenue, B = next 15%, C = the rest.
WITH product_revenue AS (
    SELECT product_id, SUM(revenue) AS revenue
    FROM fact_inventory
    GROUP BY product_id
),
cumulative AS (
    SELECT
        product_id,
        revenue,
        SUM(revenue) OVER (ORDER BY revenue DESC, product_id) AS cum_revenue,
        SUM(revenue) OVER ()                                  AS total_revenue
    FROM product_revenue
)
SELECT
    c.product_id,
    p.product_name,
    p.category,
    ROUND(c.revenue, 2)                                                              AS revenue,
    ROUND(100.0 * c.cum_revenue / c.total_revenue, 2)                                AS cumulative_revenue_pct,
    CASE
        WHEN 1.0 * c.cum_revenue / c.total_revenue <= 0.80 THEN 'A'
        WHEN 1.0 * c.cum_revenue / c.total_revenue <= 0.95 THEN 'B'
        ELSE 'C'
    END                                                                              AS abc_class
FROM cumulative c
JOIN dim_product p ON p.product_id = c.product_id
ORDER BY c.revenue DESC, c.product_id;

-- name: abc_summary
WITH product_revenue AS (
    SELECT product_id, SUM(revenue) AS revenue
    FROM fact_inventory
    GROUP BY product_id
),
cumulative AS (
    SELECT
        product_id,
        revenue,
        SUM(revenue) OVER (ORDER BY revenue DESC, product_id) AS cum_revenue,
        SUM(revenue) OVER ()                                  AS total_revenue
    FROM product_revenue
),
classified AS (
    SELECT
        revenue,
        total_revenue,
        CASE
            WHEN 1.0 * cum_revenue / total_revenue <= 0.80 THEN 'A'
            WHEN 1.0 * cum_revenue / total_revenue <= 0.95 THEN 'B'
            ELSE 'C'
        END AS abc_class
    FROM cumulative
)
SELECT
    abc_class,
    COUNT(*)                                                                         AS products,
    ROUND(SUM(revenue), 2)                                                           AS revenue,
    ROUND(100.0 * SUM(revenue) / MAX(total_revenue), 2)                              AS revenue_share_pct
FROM classified
GROUP BY abc_class
ORDER BY abc_class;

-- name: slow_movers
-- Products with the most days of stock on hand (needs at least 5 snapshots to be meaningful).
SELECT
    p.product_id,
    p.product_name,
    p.category,
    COUNT(*)                                                                         AS snapshots,
    ROUND(AVG(f.units_sold), 2)                                                      AS avg_units_sold,
    ROUND(AVG(f.inventory_level), 1)                                                 AS avg_inventory_level,
    ROUND(1.0 * AVG(f.inventory_level) / NULLIF(AVG(f.units_sold), 0), 2)            AS days_sales_of_inventory
FROM fact_inventory f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.product_id, p.product_name, p.category
HAVING COUNT(*) >= 5
ORDER BY days_sales_of_inventory DESC
LIMIT 10;

-- =====================================================================================
-- 4. Pricing, promotions and seasonality
-- =====================================================================================

-- name: price_vs_competitor_by_category
SELECT
    p.category,
    ROUND(AVG(f.unit_price), 2)                                                      AS avg_our_price,
    ROUND(AVG(f.competitor_price), 2)                                                AS avg_competitor_price,
    ROUND(100.0 * (AVG(f.unit_price) / AVG(f.competitor_price) - 1), 2)              AS price_difference_pct
FROM fact_inventory f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.category
ORDER BY p.category;

-- name: promotion_effect
SELECT
    is_promotion,
    COUNT(*)                                                                         AS snapshots,
    ROUND(AVG(units_sold), 2)                                                        AS avg_units_sold,
    ROUND(AVG(revenue), 2)                                                           AS avg_revenue
FROM fact_inventory
GROUP BY is_promotion
ORDER BY is_promotion;

-- name: holiday_effect
SELECT
    d.is_holiday,
    COUNT(*)                                                                         AS snapshots,
    ROUND(AVG(f.units_sold), 2)                                                      AS avg_units_sold,
    ROUND(AVG(f.revenue), 2)                                                         AS avg_revenue
FROM fact_inventory f
JOIN dim_date d ON d.date_id = f.date_id
GROUP BY d.is_holiday
ORDER BY d.is_holiday;
