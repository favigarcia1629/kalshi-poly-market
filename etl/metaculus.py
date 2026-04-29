"""
Metaculus ETL — fetches prediction question metadata and probability history.
Metaculus API: https://www.metaculus.com/api2/  (fully public, no auth required)

Metaculus covers macro/economic questions perfectly:
  - Fed rate decisions
  - Recession probability
  - Inflation targets
  - Bitcoin/crypto milestones
"""
import time
import requests
import pandas as pd
from datetime import date, timedelta

BASE_URL = "https://www.metaculus.com/api2"

TARGET_KEYWORDS = {
    "fed_rates":  ["fed", "federal reserve", "rate cut", "rate hike", "fomc", "interest rate",
                   "fed funds", "basis points", "monetary policy"],
    "recession":  ["recession", "gdp contraction", "economic contraction"],
    "bitcoin":    ["bitcoin", "btc", "crypto", "cryptocurrency"],
    "economy":    ["inflation", "cpi", "unemployment", "jobs report", "tariff", "gdp"],
}

HEADERS = {"Accept": "application/json"}
LOOKBACK_DAYS = 365


def _get(endpoint: str, params: dict = None, retries: int = 3) -> dict:
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Metaculus HTTP {r.status_code}: {e}")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Metaculus request failed: {e}")
            time.sleep(1)
    return {}


def _classify(title: str) -> str | None:
    title_lower = title.lower()
    for category, keywords in TARGET_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return None


def fetch_markets(limit: int = 200) -> list[dict]:
    """
    Returns Metaculus questions matching our target categories.
    Each dict: market_id, title, category, event_type, resolution_date.
    """
    results  = []
    offset   = 0
    page_sz  = 100

    while offset < limit:
        try:
            data = _get(
                "/questions/",
                params={
                    "limit":        page_sz,
                    "offset":       offset,
                    "status":       "open",
                    "type":         "forecast",
                    "order_by":     "-activity",
                    "include_description": "false",
                },
            )
        except Exception as e:
            print(f"  [Metaculus] fetch failed at offset {offset}: {e}")
            break

        questions = data.get("results", [])
        if not questions:
            break

        for q in questions:
            title = q.get("title", "")
            category = _classify(title)
            if category is None:
                continue

            close_time = q.get("close_time") or q.get("resolve_time") or ""
            results.append({
                "market_id":       str(q["id"]),
                "title":           title,
                "category":        category,
                "event_type":      q.get("page_url", "")[-50:],
                "resolution_date": close_time[:10] if close_time else None,
            })

        offset += page_sz
        time.sleep(0.3)

        if offset >= data.get("count", limit):
            break

    return results


def fetch_market_history(question_id: str, days: int = LOOKBACK_DAYS,
                          **kwargs) -> pd.DataFrame:
    """
    Returns DataFrame with: price_date, yes_probability, volume_usd.
    Metaculus returns an aggregated community prediction time series.
    """
    try:
        data = _get(f"/questions/{question_id}/")
        forecasts = data.get("community_prediction", {})

        # Metaculus stores history under question.prediction_timeseries (older API)
        # or we can fetch aggregated forecasts
        history = data.get("prediction_timeseries") or []

        if not history:
            # Try the aggregations endpoint
            agg = _get(f"/questions/{question_id}/aggregations/",
                       params={"method": "recency_weighted"})
            history = (
                agg.get("recency_weighted", {}).get("history", [])
                or agg.get("history", [])
            )

        if not history:
            # Last resort: use single current community forecast if available
            cp = data.get("community_prediction") or {}
            full = cp.get("full") or cp.get("q2")
            if full is not None:
                return pd.DataFrame([{
                    "price_date":      date.today(),
                    "yes_probability": round(float(full), 4),
                    "volume_usd":      data.get("number_of_forecasters"),
                }])
            return pd.DataFrame()

        cutoff = date.today() - timedelta(days=days)
        rows = []
        for entry in history:
            ts = entry.get("t") or entry.get("start_time")
            prob = (
                entry.get("y")
                or entry.get("q2")
                or entry.get("p_yes")
                or (entry.get("community_prediction") or {}).get("q2")
            )
            if ts is None or prob is None:
                continue
            try:
                dt = pd.Timestamp(ts).date() if isinstance(ts, str) else pd.Timestamp(ts, unit="s").date()
            except Exception:
                continue
            if dt < cutoff:
                continue
            rows.append({
                "price_date":      dt,
                "yes_probability": round(float(prob), 4),
                "volume_usd":      entry.get("num_forecasters"),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.groupby("price_date").last().reset_index()
        return df.sort_values("price_date").reset_index(drop=True)

    except Exception as e:
        print(f"  [Metaculus] history failed for question {question_id}: {e}")
        return pd.DataFrame()
