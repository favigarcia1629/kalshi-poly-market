"""
Stock / benchmark data ETL via yfinance.
Fetches OHLCV + daily returns for SPY, QQQ, VIX, TLT, GLD, BTC-USD.
"""
import yfinance as yf
import pandas as pd
from datetime import date, timedelta

TICKERS = {
    "SPY":     "S&P 500 ETF",
    "QQQ":     "Nasdaq 100 ETF",
    "^VIX":    "CBOE Volatility Index",
    "TLT":     "20+ Year Treasury ETF",
    "GLD":     "Gold ETF",
    "BTC-USD": "Bitcoin / USD",
}

LOOKBACK_DAYS = 400


def fetch_stock_data(days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Returns a long-format DataFrame with columns:
      ticker, price_date, open_price, high_price, low_price,
      close_price, volume, daily_return
    """
    start = (date.today() - timedelta(days=days)).isoformat()
    end   = date.today().isoformat()

    all_rows = []
    for ticker in TICKERS:
        try:
            raw = yf.download(
                ticker, start=start, end=end,
                auto_adjust=True, progress=False, multi_level_index=False,
            )
            if raw.empty:
                print(f"  [yfinance] empty data for {ticker}")
                continue

            # Handle both flat and multi-level column names
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open_price", "high_price", "low_price", "close_price", "volume"]
            df.index.name = "price_date"
            df = df.reset_index()
            df["price_date"] = pd.to_datetime(df["price_date"]).dt.date
            df["ticker"]     = ticker

            df["daily_return"] = df["close_price"].pct_change().round(6)
            df["volume"] = df["volume"].fillna(0).astype("int64")

            all_rows.append(df)
            print(f"  [yfinance] {ticker}: {len(df)} rows fetched")

        except Exception as e:
            print(f"  [yfinance] failed for {ticker}: {e}")

    if not all_rows:
        raise RuntimeError("No stock data fetched — check yfinance connectivity")

    combined = pd.concat(all_rows, ignore_index=True)
    combined = combined.dropna(subset=["close_price"])
    return combined[["ticker", "price_date", "open_price", "high_price",
                      "low_price", "close_price", "volume", "daily_return"]]
