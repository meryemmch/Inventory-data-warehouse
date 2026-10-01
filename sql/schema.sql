DROP TABLE IF EXISTS fact_inventory;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_store;

CREATE TABLE dim_store (
    store_id      INTEGER       NOT NULL PRIMARY KEY,
    city          VARCHAR(50)   NOT NULL,
    state         VARCHAR(50)   NOT NULL,
    address       VARCHAR(200)  NOT NULL,
    postal_code   VARCHAR(10)   NOT NULL,
    opening_date  DATE          NOT NULL
);

CREATE TABLE dim_product (
    product_id             INTEGER        NOT NULL PRIMARY KEY,
    product_name           VARCHAR(100)   NOT NULL,
    category               VARCHAR(50)    NOT NULL,
    subcategory            VARCHAR(50)    NOT NULL,
    brand                  VARCHAR(50)    NOT NULL,
    list_price             DECIMAL(10, 2) NOT NULL,
    competitor_list_price  DECIMAL(10, 2) NOT NULL
);

CREATE TABLE dim_date (
    date_id       INTEGER      NOT NULL PRIMARY KEY,   -- yyyymmdd
    full_date     DATE         NOT NULL,
    year          INTEGER      NOT NULL,
    quarter       INTEGER      NOT NULL,
    month         INTEGER      NOT NULL,
    month_name    VARCHAR(10)  NOT NULL,
    iso_year      INTEGER      NOT NULL,
    iso_week      INTEGER      NOT NULL,
    day_of_month  INTEGER      NOT NULL,
    day_of_week   INTEGER      NOT NULL,               -- 1 = Monday ... 7 = Sunday
    day_name      VARCHAR(10)  NOT NULL,
    is_weekend    INTEGER      NOT NULL,
    is_holiday    INTEGER      NOT NULL,
    holiday_name  VARCHAR(50)
);

-- Grain: one row per store x product x day (a sparse daily snapshot).
CREATE TABLE fact_inventory (
    inventory_fact_id  INTEGER        NOT NULL PRIMARY KEY,
    date_id            INTEGER        NOT NULL,
    store_id           INTEGER        NOT NULL,
    product_id         INTEGER        NOT NULL,
    inventory_level    INTEGER        NOT NULL,
    units_sold         INTEGER        NOT NULL,
    units_ordered      INTEGER        NOT NULL,
    demand_forecast    INTEGER        NOT NULL,
    unit_price         DECIMAL(10, 2) NOT NULL,
    competitor_price   DECIMAL(10, 2) NOT NULL,
    revenue            DECIMAL(12, 2) NOT NULL,        -- units_sold * unit_price
    is_promotion       INTEGER        NOT NULL,
    CONSTRAINT uq_fact_grain UNIQUE (date_id, store_id, product_id),
    CONSTRAINT fk_fact_date    FOREIGN KEY (date_id)    REFERENCES dim_date (date_id),
    CONSTRAINT fk_fact_store   FOREIGN KEY (store_id)   REFERENCES dim_store (store_id),
    CONSTRAINT fk_fact_product FOREIGN KEY (product_id) REFERENCES dim_product (product_id),
    CONSTRAINT ck_fact_nonneg CHECK (
        inventory_level >= 0 AND units_sold >= 0 AND units_ordered >= 0 AND demand_forecast >= 0
    )
);

CREATE INDEX ix_fact_date    ON fact_inventory (date_id);
CREATE INDEX ix_fact_store   ON fact_inventory (store_id);
CREATE INDEX ix_fact_product ON fact_inventory (product_id);
