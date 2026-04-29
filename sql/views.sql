-- ============================================================
-- Views for Tableau Public exports
-- ============================================================
-- These views join prediction market probabilities with
-- stock market returns for analysis and visualization.
-- Run after schema.sql:
--   psql -d prediction_markets -f sql/views.sql

-- 1. Combined daily view: every market probability + SPY return
CREATE OR REPLACE VIEW v_market_spy_daily AS
SELECT
    pp.price_date,
    pm.source,
    pm.title,
    pm.category,
    pm.event_type,
    pp.yes_probability,
    pp.volume_usd,
    sp.close_price  AS spy_close,
    sp.daily_return AS spy_return
FROM prediction_prices pp
JOIN prediction_markets pm ON pm.id = pp.market_id
LEFT JOIN stock_prices   sp ON sp.ticker = 'SPY' AND sp.price_date = pp.price_date
ORDER BY pp.price_date, pm.category;

-- 2. Rolling 30-day correlation: Fed cut probability vs. SPY return
CREATE OR REPLACE VIEW v_fed_spy_correlation AS
SELECT
    pp.price_date,
    pm.event_type,
    pm.title,
    pp.yes_probability  AS fed_cut_prob,
    sp.daily_return     AS spy_return,
    AVG(pp.yes_probability) OVER (ORDER BY pp.price_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS prob_30d_avg,
    AVG(sp.daily_return)    OVER (ORDER BY pp.price_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS spy_return_30d_avg
FROM prediction_prices pp
JOIN prediction_markets pm ON pm.id = pp.market_id AND pm.category = 'fed_rates'
LEFT JOIN stock_prices   sp ON sp.ticker = 'SPY' AND sp.price_date = pp.price_date
ORDER BY pp.price_date;

-- 3. Recession probability vs. VIX
CREATE OR REPLACE VIEW v_recession_vix AS
SELECT
    pp.price_date,
    pm.title            AS recession_market,
    pp.yes_probability  AS recession_prob,
    vix.close_price     AS vix_level,
    spy.daily_return    AS spy_return,
    spy.close_price     AS spy_close
FROM prediction_prices pp
JOIN prediction_markets pm  ON pm.id = pp.market_id AND pm.category = 'recession'
LEFT JOIN stock_prices vix  ON vix.ticker = '^VIX' AND vix.price_date = pp.price_date
LEFT JOIN stock_prices spy  ON spy.ticker = 'SPY'   AND spy.price_date = pp.price_date
ORDER BY pp.price_date;

-- 4. Bitcoin probability vs. QQQ
CREATE OR REPLACE VIEW v_bitcoin_qqq AS
SELECT
    pp.price_date,
    pm.title            AS bitcoin_market,
    pp.yes_probability  AS btc_prob,
    btc.close_price     AS btc_price,
    qqq.close_price     AS qqq_close,
    qqq.daily_return    AS qqq_return
FROM prediction_prices pp
JOIN prediction_markets pm  ON pm.id = pp.market_id AND pm.category = 'bitcoin'
LEFT JOIN stock_prices btc  ON btc.ticker = 'BTC-USD' AND btc.price_date = pp.price_date
LEFT JOIN stock_prices qqq  ON qqq.ticker = 'QQQ'     AND qqq.price_date = pp.price_date
ORDER BY pp.price_date;

-- 5. All-market summary: latest probability per market with stock context
CREATE OR REPLACE VIEW v_latest_snapshot AS
SELECT DISTINCT ON (pm.id)
    pm.source,
    pm.category,
    pm.event_type,
    pm.title,
    pm.resolution_date,
    pp.price_date   AS latest_date,
    pp.yes_probability,
    pp.volume_usd,
    spy.close_price AS spy_close,
    spy.daily_return AS spy_return
FROM prediction_markets pm
JOIN prediction_prices pp  ON pp.market_id = pm.id
LEFT JOIN stock_prices spy ON spy.ticker = 'SPY' AND spy.price_date = pp.price_date
ORDER BY pm.id, pp.price_date DESC;
