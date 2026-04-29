"""
ETL Pipeline — orchestrates Kalshi + Polymarket + yfinance → PostgreSQL.
Runs incrementally: only inserts rows that don't already exist.
"""
import os
from datetime import date
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import pandas as pd

from etl.kalshi     import fetch_markets as kalshi_markets, fetch_market_history as kalshi_history, is_available as kalshi_available
from etl.polymarket import fetch_markets as poly_markets,  fetch_market_history as poly_history
from etl.manifold   import fetch_markets as mani_markets,  fetch_market_history as mani_history
from etl.market_data import fetch_stock_data

load_dotenv()

# Max markets per source to keep runtime reasonable
MAX_MARKETS_PER_SOURCE = 20


def _engine():
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', os.getenv('USER', 'postgres'))}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'prediction_markets')}",
    )
    return create_engine(db_url, pool_pre_ping=True)


def _upsert_market(conn, source: str, mkt: dict) -> int:
    """Insert or get market ID from prediction_markets table."""
    row = conn.execute(
        text("""
            INSERT INTO prediction_markets
                (source, market_id, title, category, event_type, resolution_date)
            VALUES
                (:source, :market_id, :title, :category, :event_type, :resolution_date)
            ON CONFLICT (source, market_id) DO UPDATE
                SET title           = EXCLUDED.title,
                    resolution_date = EXCLUDED.resolution_date
            RETURNING id
        """),
        {
            "source":          source,
            "market_id":       mkt["market_id"],
            "title":           mkt["title"][:500],
            "category":        mkt.get("category"),
            "event_type":      mkt.get("event_type", "")[:200],
            "resolution_date": mkt.get("resolution_date"),
        },
    )
    return row.fetchone()[0]


def _insert_prices(conn, db_market_id: int, df: pd.DataFrame) -> int:
    """Bulk-insert prediction prices, skipping duplicates. Returns rows inserted."""
    if df.empty:
        return 0

    df = df.copy()
    df["market_id"] = db_market_id
    df["open_interest"] = df.get("open_interest", None)

    inserted = 0
    for _, row in df.iterrows():
        result = conn.execute(
            text("""
                INSERT INTO prediction_prices
                    (market_id, price_date, yes_probability, volume_usd, open_interest)
                VALUES
                    (:market_id, :price_date, :yes_probability, :volume_usd, :open_interest)
                ON CONFLICT (market_id, price_date) DO NOTHING
            """),
            {
                "market_id":       int(db_market_id),
                "price_date":      row["price_date"],
                "yes_probability": float(row["yes_probability"]) if pd.notna(row["yes_probability"]) else None,
                "volume_usd":      float(row["volume_usd"])      if pd.notna(row.get("volume_usd")) else None,
                "open_interest":   float(row["open_interest"])   if pd.notna(row.get("open_interest")) else None,
            },
        )
        inserted += result.rowcount
    return inserted


def _insert_stock_prices(conn, df: pd.DataFrame) -> int:
    """Bulk-insert stock prices, skipping duplicates. Returns rows inserted."""
    inserted = 0
    for _, row in df.iterrows():
        result = conn.execute(
            text("""
                INSERT INTO stock_prices
                    (ticker, price_date, open_price, high_price, low_price,
                     close_price, volume, daily_return)
                VALUES
                    (:ticker, :price_date, :open_price, :high_price, :low_price,
                     :close_price, :volume, :daily_return)
                ON CONFLICT (ticker, price_date) DO NOTHING
            """),
            {
                "ticker":       row["ticker"],
                "price_date":   row["price_date"],
                "open_price":   float(row["open_price"])   if pd.notna(row["open_price"])   else None,
                "high_price":   float(row["high_price"])   if pd.notna(row["high_price"])   else None,
                "low_price":    float(row["low_price"])    if pd.notna(row["low_price"])     else None,
                "close_price":  float(row["close_price"])  if pd.notna(row["close_price"])  else None,
                "volume":       int(row["volume"])         if pd.notna(row["volume"])        else None,
                "daily_return": float(row["daily_return"]) if pd.notna(row["daily_return"]) else None,
            },
        )
        inserted += result.rowcount
    return inserted


def _log_run(conn, source: str, inserted: int, updated: int, status: str, notes: str = ""):
    conn.execute(
        text("""
            INSERT INTO etl_runs (source, records_inserted, records_updated, status, notes)
            VALUES (:source, :inserted, :updated, :status, :notes)
        """),
        {"source": source, "inserted": inserted, "updated": updated,
         "status": status, "notes": notes},
    )


def run_stock_etl(engine) -> int:
    print("\n[ETL] Fetching stock market data via yfinance...")
    df = fetch_stock_data()
    with engine.begin() as conn:
        n = _insert_stock_prices(conn, df)
        _log_run(conn, "yfinance", n, 0, "success", f"{len(df)} rows processed")
    print(f"  [ETL] Stocks: {n} rows inserted")
    return n


def run_prediction_etl(engine, source: str) -> int:
    """Runs ETL for one prediction market source ('kalshi' or 'polymarket')."""
    print(f"\n[ETL] Fetching {source} markets...")
    try:
        if source == "kalshi":
            markets = kalshi_markets()
        elif source == "manifold":
            markets = mani_markets()
        else:
            markets = poly_markets()
    except Exception as e:
        print(f"  [ETL] {source} market list failed: {e}")
        with engine.begin() as conn:
            _log_run(conn, source, 0, 0, "failed", str(e))
        return 0

    # Deduplicate by category, keep top N
    seen_categories: dict[str, int] = {}
    selected = []
    for m in markets:
        cat = m.get("category", "other")
        count = seen_categories.get(cat, 0)
        if count < 5:  # up to 5 markets per category
            selected.append(m)
            seen_categories[cat] = count + 1
        if len(selected) >= MAX_MARKETS_PER_SOURCE:
            break

    print(f"  Selected {len(selected)} {source} markets across {len(seen_categories)} categories")

    total_inserted = 0
    if source == "kalshi":
        history_fn = kalshi_history
    elif source == "polymarket":
        history_fn = poly_history
    else:
        history_fn = mani_history

    for mkt in selected:
        print(f"  [{source}] {mkt['category']}: {mkt['title'][:70]}...")
        try:
            with engine.begin() as conn:
                db_id = _upsert_market(conn, source, mkt)
                if source == "polymarket":
                    history_df = history_fn(mkt["market_id"],
                                            token_id=mkt.get("token_id"))
                else:
                    history_df = history_fn(mkt["market_id"])
                n = _insert_prices(conn, db_id, history_df)
                total_inserted += n
                print(f"    → {len(history_df)} history rows, {n} inserted")
        except Exception as e:
            print(f"    → ERROR: {e}")
            with engine.begin() as conn:
                _log_run(conn, source, 0, 0, "partial", f"{mkt['market_id']}: {e}")

    with engine.begin() as conn:
        _log_run(conn, source, total_inserted, 0, "success",
                 f"{len(selected)} markets processed")
    return total_inserted


def run_full_pipeline():
    engine = _engine()
    print(f"[ETL] Connected to PostgreSQL. Starting pipeline — {date.today()}")

    totals = {}
    totals["stocks"] = run_stock_etl(engine)

    if kalshi_available():
        totals["kalshi"] = run_prediction_etl(engine, "kalshi")
    else:
        print("\n[ETL] Kalshi: skipping (no KALSHI_API_KEY in .env)")
        print("       → Sign up free at kalshi.com → Account → API to get a key")
        totals["kalshi"] = 0

    totals["polymarket"] = run_prediction_etl(engine, "polymarket")
    totals["manifold"]   = run_prediction_etl(engine, "manifold")

    print("\n[ETL] Pipeline complete.")
    for src, n in totals.items():
        print(f"  {src:12s} → {n} rows inserted")
    return totals


if __name__ == "__main__":
    run_full_pipeline()
