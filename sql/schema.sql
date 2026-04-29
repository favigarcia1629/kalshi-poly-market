-- ============================================================
-- Prediction Markets vs. Stock Market — PostgreSQL Schema
-- ============================================================
-- Run once to initialize the database:
--   psql -d prediction_markets -f sql/schema.sql

-- Metadata for each prediction market tracked
CREATE TABLE IF NOT EXISTS prediction_markets (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR(20)  NOT NULL,   -- 'kalshi' | 'polymarket'
    market_id       VARCHAR(300) NOT NULL,
    title           TEXT         NOT NULL,
    category        VARCHAR(100),            -- 'fed_rates' | 'recession' | 'bitcoin' | 'economy'
    event_type      VARCHAR(100),            -- human-readable label for grouping
    resolution_date DATE,
    is_resolved     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (source, market_id)
);

-- Daily probability snapshots for each prediction market
CREATE TABLE IF NOT EXISTS prediction_prices (
    id              SERIAL PRIMARY KEY,
    market_id       INTEGER NOT NULL REFERENCES prediction_markets(id) ON DELETE CASCADE,
    price_date      DATE    NOT NULL,
    yes_probability NUMERIC(6,4),    -- 0.0000 to 1.0000  (e.g. 0.6732)
    volume_usd      NUMERIC(18,2),
    open_interest   NUMERIC(18,2),
    fetched_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (market_id, price_date)
);

-- Daily OHLCV for stock market benchmarks
CREATE TABLE IF NOT EXISTS stock_prices (
    id           SERIAL PRIMARY KEY,
    ticker       VARCHAR(20) NOT NULL,
    price_date   DATE        NOT NULL,
    open_price   NUMERIC(14,4),
    high_price   NUMERIC(14,4),
    low_price    NUMERIC(14,4),
    close_price  NUMERIC(14,4),
    volume       BIGINT,
    daily_return NUMERIC(10,6),   -- (close_t / close_t-1) - 1
    fetched_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE (ticker, price_date)
);

-- Audit log for every ETL run
CREATE TABLE IF NOT EXISTS etl_runs (
    id               SERIAL PRIMARY KEY,
    run_at           TIMESTAMP DEFAULT NOW(),
    source           VARCHAR(20),
    records_inserted INTEGER DEFAULT 0,
    records_updated  INTEGER DEFAULT 0,
    status           VARCHAR(20),   -- 'success' | 'partial' | 'failed'
    notes            TEXT
);

-- ============================================================
-- Indexes for fast Tableau / analysis queries
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_pred_prices_date     ON prediction_prices (price_date);
CREATE INDEX IF NOT EXISTS idx_pred_prices_market   ON prediction_prices (market_id);
CREATE INDEX IF NOT EXISTS idx_stock_prices_ticker  ON stock_prices (ticker, price_date);
CREATE INDEX IF NOT EXISTS idx_etl_runs_at          ON etl_runs (run_at);
