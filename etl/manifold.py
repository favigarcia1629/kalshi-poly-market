"""
Manifold Markets ETL — fetches prediction market data and probability history.
Manifold API: https://docs.manifold.markets/api  (fully public, no auth required)

Covers macro questions we need:
  - Fed rate decisions (FOMC outcomes)
  - Recession probability
  - Bitcoin price milestones
  - Inflation / economic data surprises
"""
import time
import requests
import pandas as pd
from datetime import date, timedelta

BASE_URL = "https://api.manifold.markets/v0"

# Search terms for each category
SEARCH_TERMS = {
    "fed_rates":  [
        "federal reserve rate", "fomc rate cut", "fed rate hike",
        "fed cut 2025", "fed cut 2026",
    ],
    "recession":  [
        "recession 2025", "us recession", "nber recession",
    ],
    "bitcoin":    [
        "bitcoin price", "btc 100k", "bitcoin 2025",
    ],
    "economy":    [
        "inflation cpi", "unemployment rate", "gdp growth",
    ],
}

HEADERS = {"Accept": "application/json"}


def _get(endpoint: str, params: dict = None, retries: int = 3) -> list | dict:
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Manifold HTTP {r.status_code}: {e}")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Manifold request failed: {e}")
            time.sleep(1)
    return []


def fetch_markets(limit: int = 200) -> list[dict]:
    """
    Searches Manifold for markets in each category.
    Returns list of dicts: market_id, title, category, event_type, resolution_date.
    """
    results = []
    seen_ids: set[str] = set()

    for category, terms in SEARCH_TERMS.items():
        for term in terms:
            try:
                markets = _get(
                    "/search-markets",
                    params={"term": term, "limit": 10, "filter": "open"},
                )
                if not isinstance(markets, list):
                    continue

                for m in markets:
                    mid = m.get("id", "")
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    close_time = m.get("closeTime")
                    resolution_date = (
                        pd.Timestamp(close_time, unit="ms").date().isoformat()
                        if close_time else None
                    )

                    results.append({
                        "market_id":       mid,
                        "title":           m.get("question", ""),
                        "category":        category,
                        "event_type":      m.get("slug", "")[:100],
                        "resolution_date": resolution_date,
                    })

            except Exception as e:
                print(f"  [Manifold] search failed for '{term}': {e}")

            time.sleep(0.2)

    return results


def fetch_market_history(market_id: str, days: int = 365,
                          **kwargs) -> pd.DataFrame:
    """
    Reconstructs a daily probability time series from the bets endpoint.
    Each bet has createdTime + probAfter — we take the last bet per day.

    Returns DataFrame with: price_date, yes_probability, volume_usd.
    """
    try:
        cutoff = date.today() - timedelta(days=days)

        # Fetch bets in pages (Manifold limits to 1000 per request)
        all_bets = []
        before   = None
        for _ in range(10):   # max 10 pages = 10,000 bets
            params = {"contractId": market_id, "limit": 1000}
            if before:
                params["before"] = before
            bets = _get("/bets", params=params)
            if not isinstance(bets, list) or not bets:
                break
            all_bets.extend(bets)
            if len(bets) < 1000:
                break
            before = bets[-1]["id"]
            time.sleep(0.2)

        if not all_bets:
            # No bets yet — return today's snapshot if available
            market = _get(f"/market/{market_id}")
            if isinstance(market, dict) and "probability" in market:
                return pd.DataFrame([{
                    "price_date":      date.today(),
                    "yes_probability": round(float(market["probability"]), 4),
                    "volume_usd":      market.get("totalLiquidity"),
                }])
            return pd.DataFrame()

        rows = []
        for bet in all_bets:
            ts   = bet.get("createdTime")
            prob = bet.get("probAfter")
            if ts is None or prob is None:
                continue
            bet_date = pd.Timestamp(ts, unit="ms").date()
            if bet_date < cutoff:
                continue
            rows.append({
                "price_date":      bet_date,
                "yes_probability": round(float(prob), 4),
                "volume_usd":      abs(float(bet.get("amount", 0) or 0)),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # Daily close: last bet probability of each day
        close_prob  = df.groupby("price_date")["yes_probability"].last()
        daily_vol   = df.groupby("price_date")["volume_usd"].sum()
        result = pd.DataFrame({"yes_probability": close_prob, "volume_usd": daily_vol}).reset_index()
        return result.sort_values("price_date").reset_index(drop=True)

    except Exception as e:
        print(f"  [Manifold] history failed for {market_id}: {e}")
        return pd.DataFrame()
