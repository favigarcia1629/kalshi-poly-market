"""
Tableau Export — reads from PostgreSQL views and writes clean CSVs
that Tableau Public Desktop can ingest directly.

Run after the ETL pipeline:
    python export_tableau.py
"""
import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")


def _engine():
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', os.getenv('USER', 'postgres'))}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'prediction_markets')}",
    )
    return create_engine(db_url, pool_pre_ping=True)


EXPORTS = {
    # filename (in exports/)   → SQL view or query
    "tableau_market_spy_daily.csv": "SELECT * FROM v_market_spy_daily",
    "tableau_fed_spy.csv":          "SELECT * FROM v_fed_spy_correlation",
    "tableau_recession_vix.csv":    "SELECT * FROM v_recession_vix",
    "tableau_bitcoin_qqq.csv":      "SELECT * FROM v_bitcoin_qqq",
    "tableau_latest_snapshot.csv":  "SELECT * FROM v_latest_snapshot",
    # Full raw tables for flexible Tableau exploration
    "tableau_all_prices.csv": """
        SELECT
            pp.price_date,
            pm.source,
            pm.category,
            pm.event_type,
            pm.title,
            pp.yes_probability,
            pp.volume_usd
        FROM prediction_prices pp
        JOIN prediction_markets pm ON pm.id = pp.market_id
        ORDER BY pp.price_date, pm.category
    """,
    "tableau_stock_prices.csv": """
        SELECT ticker, price_date, close_price, daily_return, volume
        FROM stock_prices
        ORDER BY ticker, price_date
    """,
}


def export_all():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    engine = _engine()

    for filename, query in EXPORTS.items():
        out_path = os.path.join(EXPORT_DIR, filename)
        try:
            df = pd.read_sql(query.strip(), engine)
            df.to_csv(out_path, index=False)
            print(f"  Exported {filename:45s} ({len(df):>6,} rows)")
        except Exception as e:
            print(f"  FAILED {filename}: {e}")

    print(f"\nAll CSVs written to: {EXPORT_DIR}/")
    print("Next: Open Tableau Public Desktop → Connect → Text File → select any CSV")


if __name__ == "__main__":
    print("[Tableau Export] Reading from PostgreSQL views...\n")
    export_all()
