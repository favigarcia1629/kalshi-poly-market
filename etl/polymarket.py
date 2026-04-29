"""
Polymarket ETL — fetches prediction market metadata and price history.
Uses two public APIs (no auth required):
  - Gamma Markets API: https://gamma-api.polymarket.com  (metadata)
  - CLOB API:          https://clob.polymarket.com        (price history)
"""
import time
import requests
import pandas as pd
from datetime import date, timedelta

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL  = "https://clob.polymarket.com"

TARGET_KEYWORDS = {
    "fed_rates":  ["fed", "federal reserve", "rate cut", "rate hike", "fomc", "interest rate"],
    "recession":  ["recession", "gdp", "contraction"],
    "bitcoin":    ["bitcoin", "btc"],
    "economy":    ["inflation", "cpi", "unemployment", "jobs", "tariff"],
}

HEADERS = {"Accept": "application/json"}


def _get(base_url: str, endpoint: str, params: dict = None, retries: int = 3) -> dict | list:
    url = f"{base_url}{endpoint}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Polymarket HTTP {r.status_code}: {e}")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Polymarket request failed: {e}")
            time.sleep(1)
    return {}


def _classify(title: str) -> str | None:
    title_lower = title.lower()
    for category, keywords in TARGET_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return None


def fetch_markets(limit: int = 300) -> list[dict]:
    """
    Returns a list of Polymarket markets matching our target categories.
    Each dict: market_id (condition_id), title, category, event_type, resolution_date.
    """
    results = []
    offset  = 0
    page_size = 100

    while offset < limit:
        try:
            data = _get(
                GAMMA_URL, "/markets",
                params={"active": "true", "limit": page_size, "offset": offset},
            )
        except Exception as e:
            print(f"  [Polymarket] markets fetch failed at offset {offset}: {e}")
            break

        markets = data if isinstance(data, list) else data.get("markets", [])
        if not markets:
            break

        for m in markets:
            title = m.get("question", "") or m.get("title", "")
            category = _classify(title)
            if category is None:
                continue

            condition_id = m.get("conditionId") or m.get("condition_id", "")
            if not condition_id:
                continue

            # Extract token ID for price history (CLOB uses token IDs, not condition IDs)
            tokens = m.get("tokens") or m.get("clob_token_ids") or []
            if isinstance(tokens, str):
                import json as _json
                try:
                    tokens = _json.loads(tokens)
                except Exception:
                    tokens = []
            # Use the "YES" token (index 0) for probability history
            token_id = tokens[0] if tokens else condition_id

            end_date = m.get("endDate") or m.get("end_date", "")
            results.append({
                "market_id":       condition_id,
                "token_id":        token_id,
                "title":           title,
                "category":        category,
                "event_type":      m.get("slug", ""),
                "resolution_date": end_date[:10] if end_date else None,
            })

        offset += page_size
        time.sleep(0.3)

    return results


def fetch_market_history(condition_id: str, days: int = 365,
                         token_id: str = None) -> pd.DataFrame:
    """
    Returns DataFrame with: price_date, yes_probability, volume_usd.
    Polymarket CLOB /prices-history uses token IDs (not condition IDs).
    Falls back to condition_id if no token_id is provided.
    """
    try:
        start_ts = int(pd.Timestamp(date.today() - timedelta(days=days)).timestamp())
        end_ts   = int(pd.Timestamp(date.today()).timestamp())

        # CLOB price history requires a token ID (the YES outcome token)
        lookup_id = token_id if token_id else condition_id

        data = _get(
            CLOB_URL, "/prices-history",
            params={
                "market":    lookup_id,
                "startTs":   start_ts,
                "endTs":     end_ts,
                "interval":  "max",
                "fidelity":  1440,
            },
        )

        history = data.get("history", [])
        if not history:
            return pd.DataFrame()

        rows = []
        for entry in history:
            ts = entry.get("t") or entry.get("ts")
            price = entry.get("p") or entry.get("price")
            if ts is None or price is None:
                continue
            rows.append({
                "price_date":      pd.Timestamp(ts, unit="s").date(),
                "yes_probability": round(float(price), 4),
                "volume_usd":      None,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.groupby("price_date").last().reset_index()
        return df.sort_values("price_date").reset_index(drop=True)

    except Exception as e:
        print(f"  [Polymarket] history failed for {condition_id[:20]}...: {e}")
        return pd.DataFrame()


def fetch_market_current(condition_id: str) -> dict | None:
    """Returns today's snapshot from the Gamma API."""
    try:
        data = _get(GAMMA_URL, f"/markets/{condition_id}")
        m = data if isinstance(data, dict) else {}
        price = m.get("outcomePrices") or m.get("lastTradePrice")
        if price is None:
            return None
        # outcomePrices is often "[\"0.65\", \"0.35\"]"
        if isinstance(price, str) and price.startswith("["):
            import json
            prices = json.loads(price)
            yes_prob = round(float(prices[0]), 4)
        else:
            yes_prob = round(float(price), 4)
        return {
            "price_date":      date.today(),
            "yes_probability": yes_prob,
            "volume_usd":      m.get("volume24hr") or m.get("volume"),
            "open_interest":   None,
        }
    except Exception as e:
        print(f"  [Polymarket] current snapshot failed for {condition_id[:20]}...: {e}")
        return None
