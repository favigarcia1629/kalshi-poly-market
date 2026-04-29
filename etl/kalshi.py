"""
Kalshi ETL — fetches prediction market metadata and price history.
Kalshi public API v2: https://trading-api.kalshi.com/trade-api/v2
No authentication required for public market data.
"""
import time
import requests
import pandas as pd
from datetime import date, timedelta

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"

# Markets we care about, keyed by our internal category
TARGET_KEYWORDS = {
    "fed_rates":  ["fed", "federal reserve", "rate cut", "rate hike", "fomc", "interest rate"],
    "recession":  ["recession", "gdp", "contraction"],
    "bitcoin":    ["bitcoin", "btc"],
    "economy":    ["inflation", "cpi", "unemployment", "jobs"],
}


def _headers() -> dict:
    """Build headers, optionally including a Bearer token from the environment."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    token = os.getenv("KALSHI_API_KEY")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(endpoint: str, params: dict = None, retries: int = 3) -> dict:
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Kalshi HTTP error {r.status_code}: {e}")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Kalshi request failed: {e}")
            time.sleep(1)
    return {}


def _classify(title: str) -> str | None:
    title_lower = title.lower()
    for category, keywords in TARGET_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return None


def is_available() -> bool:
    """Returns True if Kalshi API is reachable (requires API key)."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("KALSHI_API_KEY"):
        return False
    try:
        _get("/markets", params={"limit": 1, "status": "open"})
        return True
    except Exception:
        return False


def fetch_markets(limit: int = 200) -> list[dict]:
    """
    Returns a list of Kalshi markets matching our target categories.
    Each dict has: market_id, title, category, event_type, resolution_date.
    """
    results = []
    cursor = None

    while True:
        params = {"limit": min(limit, 200), "status": "open"}
        if cursor:
            params["cursor"] = cursor

        data = _get("/markets", params=params)
        markets = data.get("markets", [])

        for m in markets:
            title = m.get("title", "") or m.get("subtitle", "")
            category = _classify(title)
            if category is None:
                continue

            results.append({
                "market_id":       m.get("ticker", ""),
                "title":           title,
                "category":        category,
                "event_type":      m.get("series_ticker", ""),
                "resolution_date": m.get("close_time", "")[:10] if m.get("close_time") else None,
            })

        cursor = data.get("cursor")
        if not cursor or not markets:
            break
        time.sleep(0.3)

    return results


def fetch_market_history(market_ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: price_date, yes_probability, volume_usd.
    Kalshi returns price history as a series of {ts, yes_price} dicts.
    """
    try:
        end_ts   = int(date.today().strftime("%s") if hasattr(date.today(), "strftime") else
                       pd.Timestamp(date.today()).timestamp())
        start_ts = int(pd.Timestamp(date.today() - timedelta(days=days)).timestamp())

        data = _get(
            f"/markets/{market_ticker}/history",
            params={"limit": 1000, "min_ts": start_ts, "max_ts": end_ts},
        )
        history = data.get("history", [])
        if not history:
            return pd.DataFrame()

        rows = []
        for entry in history:
            ts = entry.get("ts") or entry.get("t")
            yes_price = entry.get("yes_price", None)
            if ts is None or yes_price is None:
                continue
            rows.append({
                "price_date":      pd.Timestamp(ts, unit="s").date(),
                "yes_probability": round(float(yes_price) / 100, 4),  # Kalshi uses cents (0-100)
                "volume_usd":      entry.get("volume", None),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.groupby("price_date").last().reset_index()
        return df.sort_values("price_date").reset_index(drop=True)

    except Exception as e:
        print(f"  [Kalshi] history failed for {market_ticker}: {e}")
        return pd.DataFrame()


def fetch_market_current(market_ticker: str) -> dict | None:
    """Returns today's snapshot: yes_probability, volume_usd, open_interest."""
    try:
        data = _get(f"/markets/{market_ticker}")
        m = data.get("market", {})
        yes_ask = m.get("yes_ask", None)
        yes_bid = m.get("yes_bid", None)
        if yes_ask is None or yes_bid is None:
            return None
        midpoint = (float(yes_ask) + float(yes_bid)) / 2.0 / 100.0
        return {
            "price_date":      date.today(),
            "yes_probability": round(midpoint, 4),
            "volume_usd":      m.get("volume", None),
            "open_interest":   m.get("open_interest", None),
        }
    except Exception as e:
        print(f"  [Kalshi] current snapshot failed for {market_ticker}: {e}")
        return None
