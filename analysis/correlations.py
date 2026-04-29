"""
Lead/Lag Correlation Analysis — Prediction Markets vs. Stock Market.
Reads from PostgreSQL, computes correlations, exports results to CSV.
"""
import os
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "exports")


def _engine():
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', os.getenv('USER', 'postgres'))}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'prediction_markets')}",
    )
    return create_engine(db_url, pool_pre_ping=True)


def load_joined_data(engine, category: str, stock_ticker: str) -> pd.DataFrame:
    """
    Returns a daily DataFrame with prediction market probability and
    stock market return joined on price_date.
    """
    query = text("""
        SELECT
            pp.price_date,
            pm.title,
            pm.event_type,
            pp.yes_probability,
            pp.volume_usd,
            sp.close_price,
            sp.daily_return
        FROM prediction_prices pp
        JOIN prediction_markets pm ON pm.id = pp.market_id
                                   AND pm.category = :category
        LEFT JOIN stock_prices sp  ON sp.ticker = :ticker
                                   AND sp.price_date = pp.price_date
        ORDER BY pm.id, pp.price_date
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"category": category, "ticker": stock_ticker})
    df["price_date"] = pd.to_datetime(df["price_date"])
    return df


def lead_lag_correlation(series_x: pd.Series, series_y: pd.Series,
                          max_lag: int = 10) -> pd.DataFrame:
    """
    Computes Pearson correlation between x and y at each lag from -max_lag to +max_lag.
    Negative lag = x leads y (x is predictive of future y).
    Positive lag = y leads x (y is predictive of future x).
    Returns a DataFrame with columns: lag, correlation, n_obs.
    """
    results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            x = series_x.iloc[:lag]
            y = series_y.iloc[-lag:]
        elif lag > 0:
            x = series_x.iloc[lag:]
            y = series_y.iloc[:-lag]
        else:
            x, y = series_x, series_y

        aligned = pd.DataFrame({"x": x.values, "y": y.values}).dropna()
        if len(aligned) < 10:
            continue
        corr = aligned["x"].corr(aligned["y"])
        results.append({"lag": lag, "correlation": round(corr, 4), "n_obs": len(aligned)})

    return pd.DataFrame(results)


def rolling_correlation(df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """
    Computes rolling Pearson correlation between yes_probability and daily_return.
    Returns the input DataFrame with an added 'rolling_corr' column.
    """
    df = df.copy().sort_values("price_date").reset_index(drop=True)
    df["rolling_corr"] = (
        df["yes_probability"].rolling(window, min_periods=15)
        .corr(df["daily_return"])
        .round(4)
    )
    return df


def quintile_analysis(df: pd.DataFrame, ticker_label: str) -> pd.DataFrame:
    """
    Buckets observations by probability quintile and computes
    average stock return in each bucket.
    """
    df = df.dropna(subset=["yes_probability", "daily_return"]).copy()
    if len(df) < 20:
        return pd.DataFrame()
    df["prob_quintile"] = pd.qcut(df["yes_probability"], q=5, labels=[1, 2, 3, 4, 5])
    summary = (
        df.groupby("prob_quintile", observed=True)
        .agg(
            prob_min=("yes_probability", "min"),
            prob_max=("yes_probability", "max"),
            avg_return=(  "daily_return",  "mean"),
            std_return=(  "daily_return",  "std"),
            n_days=(      "daily_return",  "count"),
        )
        .reset_index()
    )
    summary["stock_ticker"]   = ticker_label
    summary["annualized_ret"] = (summary["avg_return"] * 252).round(4)
    return summary


def run_analysis():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    engine = _engine()

    analyses = [
        {"category": "fed_rates",  "ticker": "SPY",     "label": "Fed Rates → SPY"},
        {"category": "recession",  "ticker": "^VIX",    "label": "Recession → VIX"},
        {"category": "recession",  "ticker": "SPY",     "label": "Recession → SPY"},
        {"category": "bitcoin",    "ticker": "BTC-USD", "label": "Bitcoin → BTC"},
        {"category": "bitcoin",    "ticker": "QQQ",     "label": "Bitcoin → QQQ"},
    ]

    all_lead_lag    = []
    all_rolling     = []
    all_quintiles   = []

    for spec in analyses:
        cat    = spec["category"]
        ticker = spec["ticker"]
        label  = spec["label"]
        print(f"\n[Analysis] {label}")

        try:
            df = load_joined_data(engine, cat, ticker)
        except Exception as e:
            print(f"  DB error: {e}")
            continue

        if df.empty:
            print("  No data available yet.")
            continue

        # Use most liquid market (most rows)
        top_market = df.groupby("title").size().idxmax()
        df_m = df[df["title"] == top_market].copy()
        print(f"  Market: {top_market[:70]}... ({len(df_m)} rows)")

        # Lead/lag
        ll = lead_lag_correlation(df_m["yes_probability"], df_m["daily_return"])
        ll["analysis"] = label
        all_lead_lag.append(ll)

        # Rolling correlation
        rc = rolling_correlation(df_m)
        rc["analysis"] = label
        all_rolling.append(rc[["price_date", "yes_probability", "daily_return",
                                "rolling_corr", "analysis"]])

        # Quintile analysis
        q = quintile_analysis(df_m, ticker)
        if not q.empty:
            q["analysis"] = label
            all_quintiles.append(q)

    # Export CSVs for Tableau
    if all_lead_lag:
        out = pd.concat(all_lead_lag, ignore_index=True)
        out.to_csv(f"{OUTPUT_DIR}/lead_lag_correlations.csv", index=False)
        print(f"\n  Saved: exports/lead_lag_correlations.csv ({len(out)} rows)")

    if all_rolling:
        out = pd.concat(all_rolling, ignore_index=True)
        out.to_csv(f"{OUTPUT_DIR}/rolling_correlations.csv", index=False)
        print(f"  Saved: exports/rolling_correlations.csv ({len(out)} rows)")

    if all_quintiles:
        out = pd.concat(all_quintiles, ignore_index=True)
        out.to_csv(f"{OUTPUT_DIR}/quintile_analysis.csv", index=False)
        print(f"  Saved: exports/quintile_analysis.csv ({len(out)} rows)")

    print("\n[Analysis] Complete. CSVs are in exports/ — import these into Tableau Public.")


if __name__ == "__main__":
    run_analysis()
