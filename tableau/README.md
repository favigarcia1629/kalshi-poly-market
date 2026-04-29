# Connecting Tableau Public to This Project

## Step 1 — Install Tableau Public Desktop (free)
Download from: https://public.tableau.com/en-us/s/download

## Step 2 — Run the ETL pipeline
```bash
cd prediction_markets
python run_etl.py
```
This populates PostgreSQL and writes CSVs to `exports/`.

## Step 3 — Open Tableau Public Desktop
1. Click **Connect → To a File → Text File**
2. Navigate to `prediction_markets/exports/`
3. Start with `tableau_all_prices.csv` + `tableau_stock_prices.csv`

## Recommended Dashboard Structure

### Sheet 1 — Probability Timeline
- Rows: `Yes Probability` (line chart)
- Columns: `Price Date`
- Color: `Category` (Fed Rates, Recession, Bitcoin)
- Filter: `Source` (Kalshi / Polymarket)

### Sheet 2 — Lead/Lag Correlation Bar Chart
- Data: `lead_lag_correlations.csv`
- Rows: `Correlation`
- Columns: `Lag` (-10 to +10)
- Color: green if positive, red if negative
- **Key insight:** if bar at Lag=-1 is tallest, prediction markets lead stocks by 1 day

### Sheet 3 — Rolling 30-Day Correlation
- Data: `rolling_correlations.csv`
- Line chart of `Rolling Corr` over time
- Reference line at 0 (color flip positive/negative)

### Sheet 4 — Probability Quintile vs. Return
- Data: `quintile_analysis.csv`
- Bar chart: X = `Prob Quintile`, Y = `Annualized Return`
- Shows: do higher cut probabilities → higher returns?

### Sheet 5 — Recession Probability vs. VIX Scatter
- Data: `tableau_recession_vix.csv`
- Scatter: X = `Recession Prob`, Y = `VIX Level`
- Color by year, trend line

## Publishing to Tableau Public
1. Build your workbook
2. **File → Save to Tableau Public As...**
3. Sign in with your free Tableau Public account
4. Choose visibility (public)
5. Copy the published URL for your portfolio

## Connecting Directly to PostgreSQL (Tableau Desktop only)
If you have Tableau Desktop (paid), you can connect live:
- Server: `localhost`
- Port: `5432`
- Database: `prediction_markets`
- Authentication: username only (no password for local)
- Start with the views: `v_market_spy_daily`, `v_fed_spy_correlation`, etc.
