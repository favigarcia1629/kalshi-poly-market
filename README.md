# Prediction Markets vs. Stock Markets

**Do prediction market probabilities on macro events lead, lag, or correlate with stock market movements?**

🔗 **[Live Interactive Dashboard](https://public.tableau.com/app/profile/favianesi.garcia/viz/PredictionMarketsvsStockMarket/Dashboard1)**

This project builds a real data pipeline: Python ETL pulls live prediction market data from Manifold Markets and Polymarket, stores it in PostgreSQL, and feeds Tableau Public for interactive visual analysis.

---

## The Question

Prediction markets aggregate crowd wisdom into a single probability — things like "Will the Fed cut rates in June?" or "Will the US enter recession in 2025?" If markets are efficient, these probabilities should already be priced into stocks. But do they lead? Do they lag? Or are they correlated in real time?

This project tests it with live data.

---

## Research Questions

| Question | Metrics |
|---|---|
| Does rising Fed cut probability correlate with SPY gains? | Pearson correlation, quintile analysis |
| Do prediction market prices *lead* stock market moves? | Lead/lag correlation at -10 to +10 days |
| Does recession probability track with VIX? | Correlation, scatter plot |
| Does Bitcoin prediction market probability lead BTC price? | Same lead/lag framework |

---

## Key Findings (preliminary, live data)

| Relationship | Direction | Notes |
|---|---|---|
| Fed cut probability → SPY | Positive correlation | Rising cut odds = bullish for equities |
| Recession probability → VIX | Positive correlation | High recession odds = elevated fear |
| Bitcoin market → QQQ | Positive correlation | Crypto optimism tracks tech equities |

*Analysis updates every time the ETL runs.*

---

## Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Data Sources | Manifold Markets API, Polymarket API | Prediction market probabilities |
| Market Data | yfinance | SPY, QQQ, VIX, TLT, GLD, BTC-USD daily OHLCV |
| ETL Pipeline | Python (requests, pandas, SQLAlchemy) | Fetch → clean → load |
| Database | PostgreSQL 16 | Structured storage with views for analysis |
| Analysis | Python (pandas, numpy) | Lead/lag correlations, quintile buckets |
| Visualization | Tableau Public | Interactive dashboard |
| Version Control | GitHub | Code only — data stays local |

---

## Project Structure

```
prediction_markets/
├── etl/
│   ├── manifold.py       # Manifold Markets API — market list + bet history
│   ├── polymarket.py     # Polymarket Gamma API — market snapshots
│   ├── kalshi.py         # Kalshi API — requires free API key
│   ├── market_data.py    # yfinance — SPY, QQQ, VIX, TLT, GLD, BTC-USD
│   └── pipeline.py       # Orchestrates all sources → PostgreSQL
├── sql/
│   ├── schema.sql        # Table definitions + indexes
│   ├── views.sql         # Joined views for Tableau
│   └── analysis.sql      # Research queries (correlation, quintiles, regimes)
├── analysis/
│   └── correlations.py   # Lead/lag analysis + CSV export
├── exports/              # CSVs for Tableau (gitignored)
├── tableau/
│   └── README.md         # Tableau connection instructions
├── export_tableau.py     # Reads PostgreSQL views → writes CSVs
├── run_etl.py            # Main entry point
├── requirements.txt
└── .env                  # DB credentials + optional API keys (gitignored)
```

---

## Database Schema

```sql
prediction_markets  -- one row per tracked market/question
prediction_prices   -- daily probability snapshots
stock_prices        -- daily OHLCV for SPY, QQQ, VIX, TLT, GLD, BTC
etl_runs            -- audit log for every pipeline execution
```

**Views for Tableau:**
- `v_market_spy_daily` — every prediction market joined to SPY
- `v_fed_spy_correlation` — Fed cut probability + SPY with rolling averages
- `v_recession_vix` — recession probability + VIX
- `v_bitcoin_qqq` — Bitcoin probability + QQQ

---

## Run Locally

```bash
git clone https://github.com/favigarcia1629/prediction-markets.git
cd prediction-markets

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL (if not already running)
brew services start postgresql@16

# Initialize the database (first time only)
psql -d prediction_markets -f sql/schema.sql
psql -d prediction_markets -f sql/views.sql

# Run full pipeline: fetch data → load PostgreSQL → export CSVs
python run_etl.py

# Stocks only (fast refresh)
python run_etl.py --stocks

# Export CSVs only (skip API calls)
python run_etl.py --export

# Run lead/lag analysis
python run_etl.py --analysis
```

---

## Adding a Kalshi API Key (optional)

Kalshi has deeper liquidity on Fed/macro markets. A free account gives API access:
1. Sign up at [kalshi.com](https://kalshi.com)
2. Go to Account → API → Generate Key
3. Add to `.env`:
   ```
   KALSHI_API_KEY=your_key_here
   ```
4. Re-run `python run_etl.py`

---

## Exploring with SQL

```bash
# Connect to the database
psql -d prediction_markets

# Run the analysis queries
\i sql/analysis.sql

# Check what data we have
SELECT source, category, COUNT(*) FROM prediction_markets GROUP BY 1, 2;
```

---

## Methodology Notes

- Prediction market probabilities represent the **crowd's implied probability** of an event
- Manifold uses a **continuous double auction** market maker (CFMM)
- Daily probability is the **closing price** of the last bet of each trading day
- Lead/lag analysis tests whether **t-day changes in probability predict t+n-day stock returns**
- All correlations are Pearson with sample sizes reported
- Stock data: adjusted close prices via yfinance

---

*Data: Manifold Markets API, Polymarket Gamma API, Yahoo Finance via yfinance. Not financial advice — built for research and education.*
