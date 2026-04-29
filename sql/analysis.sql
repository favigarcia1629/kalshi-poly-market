-- ============================================================
-- Analysis Queries — Prediction Markets vs. Stock Market
-- ============================================================
-- Run interactively or via psql:
--   psql -d prediction_markets -f sql/analysis.sql

-- ── 1. How many days of data do we have per market? ─────────
SELECT
    pm.source,
    pm.category,
    pm.event_type,
    COUNT(pp.id)        AS trading_days,
    MIN(pp.price_date)  AS first_date,
    MAX(pp.price_date)  AS last_date,
    ROUND(AVG(pp.yes_probability)::NUMERIC, 3) AS avg_probability
FROM prediction_markets pm
JOIN prediction_prices pp ON pp.market_id = pm.id
GROUP BY pm.source, pm.category, pm.event_type
ORDER BY pm.category, trading_days DESC;


-- ── 2. Pearson correlation: Fed cut probability vs. SPY ─────
-- A positive number means rising cut probability → rising SPY
-- A negative number means rising cut prob → falling SPY
WITH daily AS (
    SELECT
        pp.price_date,
        pp.yes_probability AS fed_prob,
        sp.daily_return    AS spy_return
    FROM prediction_prices pp
    JOIN prediction_markets pm ON pm.id = pp.market_id
                               AND pm.category = 'fed_rates'
    JOIN stock_prices sp       ON sp.ticker = 'SPY'
                               AND sp.price_date = pp.price_date
    WHERE sp.daily_return IS NOT NULL
)
SELECT
    ROUND(CORR(fed_prob, spy_return)::NUMERIC, 4)           AS corr_same_day,
    ROUND(CORR(LAG(fed_prob) OVER (ORDER BY price_date),
               spy_return)::NUMERIC, 4)                      AS corr_prob_1d_lead,
    COUNT(*)                                                  AS n_observations
FROM daily;


-- ── 3. Correlation: Recession probability vs. VIX ───────────
WITH daily AS (
    SELECT
        pp.price_date,
        pp.yes_probability   AS rec_prob,
        vix.close_price      AS vix_level
    FROM prediction_prices pp
    JOIN prediction_markets pm ON pm.id = pp.market_id
                               AND pm.category = 'recession'
    JOIN stock_prices vix      ON vix.ticker = '^VIX'
                               AND vix.price_date = pp.price_date
    WHERE vix.close_price IS NOT NULL
)
SELECT
    ROUND(CORR(rec_prob, vix_level)::NUMERIC, 4)   AS corr_recession_vix,
    ROUND(AVG(rec_prob)::NUMERIC, 3)               AS avg_recession_prob,
    ROUND(AVG(vix_level)::NUMERIC, 2)              AS avg_vix,
    COUNT(*)                                        AS n_observations
FROM daily;


-- ── 4. Does prediction market probability lead stock prices? ─
-- If corr_lead > corr_same_day, PM probability is predictive
WITH fed_spy AS (
    SELECT
        pp.price_date,
        pp.yes_probability                                      AS prob_t,
        LEAD(pp.yes_probability)    OVER (ORDER BY pp.price_date) AS prob_t1,
        sp.daily_return                                         AS ret_t,
        LEAD(sp.daily_return, 1)    OVER (ORDER BY pp.price_date) AS ret_t1,
        LEAD(sp.daily_return, 2)    OVER (ORDER BY pp.price_date) AS ret_t2,
        LEAD(sp.daily_return, 5)    OVER (ORDER BY pp.price_date) AS ret_t5
    FROM prediction_prices pp
    JOIN prediction_markets pm ON pm.id = pp.market_id
                               AND pm.category = 'fed_rates'
    JOIN stock_prices sp       ON sp.ticker = 'SPY'
                               AND sp.price_date = pp.price_date
)
SELECT
    ROUND(CORR(prob_t, ret_t )::NUMERIC, 4) AS corr_t0,
    ROUND(CORR(prob_t, ret_t1)::NUMERIC, 4) AS corr_t1_lag,
    ROUND(CORR(prob_t, ret_t2)::NUMERIC, 4) AS corr_t2_lag,
    ROUND(CORR(prob_t, ret_t5)::NUMERIC, 4) AS corr_t5_lag
FROM fed_spy;


-- ── 5. Probability quintile buckets vs. average SPY return ──
-- Do higher Fed-cut probabilities correspond to higher SPY returns?
WITH buckets AS (
    SELECT
        pp.price_date,
        pp.yes_probability,
        sp.daily_return,
        NTILE(5) OVER (ORDER BY pp.yes_probability) AS prob_quintile
    FROM prediction_prices pp
    JOIN prediction_markets pm ON pm.id = pp.market_id
                               AND pm.category = 'fed_rates'
    JOIN stock_prices sp       ON sp.ticker = 'SPY'
                               AND sp.price_date = pp.price_date
    WHERE sp.daily_return IS NOT NULL
)
SELECT
    prob_quintile,
    ROUND(MIN(yes_probability)::NUMERIC, 3)  AS prob_min,
    ROUND(MAX(yes_probability)::NUMERIC, 3)  AS prob_max,
    ROUND(AVG(daily_return)::NUMERIC, 5)     AS avg_spy_return,
    ROUND(STDDEV(daily_return)::NUMERIC, 5)  AS std_spy_return,
    COUNT(*)                                  AS n_days
FROM buckets
GROUP BY prob_quintile
ORDER BY prob_quintile;


-- ── 6. Market regime: SPY return when recession prob > 50% ──
SELECT
    CASE
        WHEN pp.yes_probability >= 0.50 THEN 'High Recession Risk (>= 50%)'
        WHEN pp.yes_probability >= 0.30 THEN 'Moderate Risk (30-50%)'
        ELSE 'Low Risk (< 30%)'
    END                                           AS recession_regime,
    COUNT(*)                                       AS n_days,
    ROUND(AVG(sp.daily_return)::NUMERIC, 5)        AS avg_spy_return,
    ROUND(STDDEV(sp.daily_return)::NUMERIC, 5)     AS std_spy_return,
    ROUND((AVG(sp.daily_return) * 252)::NUMERIC, 4) AS annualized_return
FROM prediction_prices pp
JOIN prediction_markets pm ON pm.id = pp.market_id
                           AND pm.category = 'recession'
JOIN stock_prices sp       ON sp.ticker = 'SPY'
                           AND sp.price_date = pp.price_date
WHERE sp.daily_return IS NOT NULL
GROUP BY recession_regime
ORDER BY avg_spy_return DESC;


-- ── 7. Bitcoin probability vs. QQQ returns ──────────────────
WITH daily AS (
    SELECT
        pp.price_date,
        pp.yes_probability  AS btc_prob,
        qqq.daily_return    AS qqq_return
    FROM prediction_prices pp
    JOIN prediction_markets pm ON pm.id = pp.market_id
                               AND pm.category = 'bitcoin'
    JOIN stock_prices qqq      ON qqq.ticker = 'QQQ'
                               AND qqq.price_date = pp.price_date
    WHERE qqq.daily_return IS NOT NULL
)
SELECT
    ROUND(CORR(btc_prob, qqq_return)::NUMERIC, 4)  AS corr_btc_prob_qqq,
    COUNT(*)                                         AS n_observations
FROM daily;


-- ── 8. ETL audit: recent runs ────────────────────────────────
SELECT
    run_at,
    source,
    records_inserted,
    records_updated,
    status,
    notes
FROM etl_runs
ORDER BY run_at DESC
LIMIT 20;
