"""
Generates a professional PDF report for the Prediction Markets vs. Stock Market project.
Usage: python generate_pdf.py
"""
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

OUTPUT = Path(__file__).parent / "exports" / "Prediction_Markets_Report.pdf"

RED    = colors.HexColor("#E74C3C")
BLUE   = colors.HexColor("#3498DB")
GREEN  = colors.HexColor("#27AE60")
DARK   = colors.HexColor("#1A1A2E")
ACCENT = colors.HexColor("#0D47A1")
LIGHT  = colors.HexColor("#F5F5F5")
GOLD   = colors.HexColor("#F39C12")
GRAY   = colors.HexColor("#888888")
PURPLE = colors.HexColor("#8E44AD")


def _engine():
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', os.getenv('USER', 'postgres'))}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'prediction_markets')}",
    )
    return create_engine(db_url, pool_pre_ping=True)


def load_data():
    engine = _engine()
    with engine.connect() as conn:
        markets = pd.read_sql(
            "SELECT source, category, COUNT(*) as n FROM prediction_markets GROUP BY source, category ORDER BY category",
            conn
        )
        prices = pd.read_sql(
            "SELECT COUNT(*) as total_rows, MIN(price_date) as earliest, MAX(price_date) as latest FROM prediction_prices",
            conn
        )
        stocks = pd.read_sql(
            "SELECT COUNT(*) as rows, MIN(price_date) as earliest, MAX(price_date) as latest FROM stock_prices",
            conn
        )
        latest = pd.read_sql(text("""
            SELECT pm.category, pm.title, pp.yes_probability, pp.price_date
            FROM prediction_prices pp
            JOIN prediction_markets pm ON pm.id = pp.market_id
            WHERE pp.price_date = (SELECT MAX(price_date) FROM prediction_prices pp2 WHERE pp2.market_id = pm.id)
            ORDER BY pm.category, pp.yes_probability DESC
        """), conn)
        etl_runs = pd.read_sql(
            "SELECT source, SUM(records_inserted) as inserted, MAX(run_at) as last_run FROM etl_runs GROUP BY source ORDER BY source",
            conn
        )
    return markets, prices, stocks, latest, etl_runs


def build_styles():
    S = {}
    S["cover_title"] = ParagraphStyle(
        "cover_title", fontSize=24, fontName="Helvetica-Bold",
        textColor=DARK, alignment=TA_CENTER, spaceAfter=8, leading=30,
    )
    S["cover_sub"] = ParagraphStyle(
        "cover_sub", fontSize=12, fontName="Helvetica",
        textColor=colors.HexColor("#555555"), alignment=TA_CENTER, spaceAfter=4,
    )
    S["cover_date"] = ParagraphStyle(
        "cover_date", fontSize=10, fontName="Helvetica",
        textColor=GRAY, alignment=TA_CENTER,
    )
    S["section_header"] = ParagraphStyle(
        "section_header", fontSize=16, fontName="Helvetica-Bold",
        textColor=ACCENT, spaceBefore=18, spaceAfter=6, leading=20,
    )
    S["sub_header"] = ParagraphStyle(
        "sub_header", fontSize=12, fontName="Helvetica-Bold",
        textColor=DARK, spaceBefore=12, spaceAfter=4,
    )
    S["body"] = ParagraphStyle(
        "body", fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#222222"), leading=16,
        alignment=TA_JUSTIFY, spaceAfter=6,
    )
    S["linkedin"] = ParagraphStyle(
        "linkedin", fontSize=10.5, fontName="Helvetica",
        textColor=colors.HexColor("#1a1a1a"), leading=17,
        alignment=TA_LEFT, spaceAfter=6, leftIndent=12, rightIndent=12,
    )
    S["disclaimer"] = ParagraphStyle(
        "disclaimer", fontSize=8, fontName="Helvetica-Oblique",
        textColor=GRAY, alignment=TA_CENTER, spaceAfter=4,
    )
    return S


def build_pdf():
    os.makedirs(OUTPUT.parent, exist_ok=True)
    print("Loading data from PostgreSQL...")
    markets, prices, stocks, latest, etl_runs = load_data()

    total_markets   = int(markets["n"].sum())
    total_price_rows = int(prices["total_rows"].iloc[0])
    stock_rows      = int(stocks["rows"].iloc[0])
    earliest        = str(prices["earliest"].iloc[0])[:10]
    latest_date     = str(prices["latest"].iloc[0])[:10]

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=letter,
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
    )
    S = build_styles()
    story = []

    # ── COVER ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("Prediction Markets vs. Stock Markets", S["cover_title"]))
    story.append(Spacer(1, 0.1*inch))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Do crowd-sourced macro probabilities lead, lag, or correlate with equity markets?",
        S["cover_date"]
    ))
    story.append(Paragraph(
        f"Manifold Markets + Polymarket + yfinance · PostgreSQL · "
        f"Generated {date.today().strftime('%B %d, %Y')}",
        S["cover_date"]
    ))
    story.append(Spacer(1, 0.4*inch))

    # KPI box
    kpi_data = [[
        Paragraph(
            f"<b>{total_markets} Markets Tracked</b>  |  "
            f"<b>{total_price_rows:,} Probability Snapshots</b>  |  "
            f"<b>{stock_rows:,} Stock Price Rows</b>  |  "
            f"<b>{earliest} → {latest_date}</b>",
            ParagraphStyle("kpi", fontSize=11, fontName="Helvetica-Bold",
                           textColor=colors.white, alignment=TA_CENTER)
        )
    ]]
    kpi_box = Table(kpi_data, colWidths=[6.5*inch])
    kpi_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), ACCENT),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
    ]))
    story.append(kpi_box)
    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph(
        "Prediction markets aggregate collective intelligence into a single number — "
        "the crowd's probability of a macro event. This project tests whether that number "
        "moves before, with, or after equity markets.",
        S["cover_sub"]
    ))

    story.append(PageBreak())

    # ── SECTION 1: LinkedIn Post ───────────────────────────────────────────────
    story.append(Paragraph("Section 1 — LinkedIn Post Draft", S["section_header"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 0.1*inch))

    linkedin_lines = [
        "Prediction markets price macro events in real time.",
        "Stock markets price company cash flows.",
        "",
        "Do they talk to each other?",
        "",
        "I built a data pipeline to find out.",
        "",
        "I pulled live prediction market probabilities from Manifold Markets",
        "and Polymarket — tracking 20 markets across four macro themes:",
        "",
        "   Fed rate decisions (FOMC outcomes)",
        "   US recession probability",
        "   Bitcoin price milestones",
        "   Inflation / CPI surprises",
        "",
        "Then I joined those daily probabilities to SPY, QQQ, VIX, TLT,",
        "and BTC prices in a PostgreSQL database.",
        "",
        "The research question: does prediction market probability LEAD",
        "stock market returns — or does it just reflect them?",
        "",
        "Lead/lag correlation analysis at -10 to +10 day offsets tells us:",
        "   Negative lag = prediction market leads stocks",
        "   Zero lag = they move together",
        "   Positive lag = stocks lead prediction markets",
        "",
        "The infrastructure:",
        "   Python ETL pipeline → PostgreSQL 16",
        "   SQL views for joined analysis",
        "   pandas lead/lag correlation engine",
        "   Tableau-ready CSV exports",
        "",
        "This is the kind of alternative data analysis that quantitative",
        "hedge funds run at scale. I built the framework from scratch.",
        "",
        "Full code and SQL schema on GitHub.",
        "",
        "#PredictionMarkets #Quant #AlternativeData #SQL #Python #Finance",
    ]

    for line in linkedin_lines:
        if line == "":
            story.append(Spacer(1, 0.07*inch))
        else:
            story.append(Paragraph(line, S["linkedin"]))

    story.append(PageBreak())

    # ── SECTION 2: Thought Process ────────────────────────────────────────────
    story.append(Paragraph("Section 2 — Project Thought Process", S["section_header"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 0.08*inch))

    story.append(Paragraph("The Question", S["sub_header"]))
    story.append(Paragraph(
        "Prediction markets are one of the most information-dense signals in finance. When the crowd "
        "prices a 70% probability of a Fed rate cut, that belief should already be priced into equities — "
        "or should it? If prediction markets aggregate dispersed private information faster than equity "
        "markets, their probabilities might lead stock prices. If they lag, equity markets are more "
        "informationally efficient. This project builds the infrastructure to test that question with "
        "live data across multiple macro themes.",
        S["body"]
    ))

    story.append(Paragraph("Why This Tech Stack?", S["sub_header"]))
    story.append(Paragraph(
        "The project was intentionally designed to demonstrate a different skill set from standard "
        "data science projects. Rather than a Streamlit dashboard reading CSVs, this is a production-style "
        "data pipeline: REST API calls → data cleaning → PostgreSQL ingestion → SQL views → "
        "analytical exports. This mirrors how quantitative research teams actually work — "
        "with structured databases, incremental ETL runs, and audit logs.",
        S["body"]
    ))

    story.append(Paragraph("Markets Tracked", S["sub_header"]))

    if not latest.empty:
        mkt_data = [["Category", "Market Title", "Latest Probability"]]
        for _, row in latest.iterrows():
            mkt_data.append([
                row["category"].replace("_", " ").title(),
                row["title"][:55] + "..." if len(str(row["title"])) > 55 else str(row["title"]),
                f"{float(row['yes_probability'])*100:.1f}%",
            ])
        mt = Table(mkt_data, colWidths=[1.3*inch, 4.2*inch, 1.0*inch])
        mt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  ACCENT),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 8),
            ("ALIGN",         (2,0),(-1,-1), "CENTER"),
            ("ALIGN",         (0,0),(1,-1),  "LEFT"),
            ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [LIGHT, colors.white]),
            ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCCCCC")),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ]))
        story.append(mt)

    story.append(PageBreak())

    # ── SECTION 3: Database Architecture ─────────────────────────────────────
    story.append(Paragraph("Section 3 — Database Architecture", S["section_header"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 0.08*inch))

    story.append(Paragraph("PostgreSQL Schema", S["sub_header"]))
    schema_data = [[
        Paragraph(
            "<b>prediction_markets</b> — one row per tracked market<br/>"
            "  id, source, market_id, title, category, event_type, resolution_date<br/><br/>"
            "<b>prediction_prices</b> — daily probability snapshots<br/>"
            "  id, market_id (FK), price_date, yes_probability, volume_usd, open_interest<br/><br/>"
            "<b>stock_prices</b> — daily OHLCV for SPY, QQQ, VIX, TLT, GLD, BTC-USD<br/>"
            "  id, ticker, price_date, open/high/low/close, volume, daily_return<br/><br/>"
            "<b>etl_runs</b> — audit log for every pipeline execution<br/>"
            "  id, run_at, source, records_inserted, records_updated, status, notes",
            ParagraphStyle("schema", fontSize=9.5, fontName="Helvetica",
                          textColor=DARK, leading=16, leftIndent=8)
        )
    ]]
    schema_box = Table(schema_data, colWidths=[6.5*inch])
    schema_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#F0F7FF")),
        ("BOX",           (0,0),(-1,-1), 1, ACCENT),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
    ]))
    story.append(schema_box)
    story.append(Spacer(1, 0.12*inch))

    story.append(Paragraph("SQL Views for Analysis", S["sub_header"]))
    views_data = [
        ["View",                    "Purpose"],
        ["v_market_spy_daily",      "Every prediction market probability joined to SPY daily returns"],
        ["v_fed_spy_correlation",   "Fed cut probability + SPY with 30-day rolling averages"],
        ["v_recession_vix",         "Recession probability joined to VIX levels and SPY returns"],
        ["v_bitcoin_qqq",           "Bitcoin probability joined to BTC price and QQQ returns"],
        ["v_latest_snapshot",       "Most recent probability per market with stock market context"],
    ]
    vt = Table(views_data, colWidths=[2.2*inch, 4.3*inch])
    vt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ACCENT),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("ALIGN",         (0,0),(-1,-1), "LEFT"),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [LIGHT, colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]))
    story.append(vt)

    story.append(PageBreak())

    # ── SECTION 4: Methods & Tools ────────────────────────────────────────────
    story.append(Paragraph("Section 4 — Methods & Tools", S["section_header"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 0.08*inch))

    story.append(Paragraph("Lead/Lag Correlation Framework", S["sub_header"]))
    ll_data = [[
        Paragraph(
            "For each prediction market category, the analysis computes Pearson correlation "
            "between the market probability at time <i>t</i> and stock returns at time <i>t+n</i> "
            "for n = -10 to +10 trading days:<br/><br/>"
            "<b>Lag = -1:</b> Does today's probability predict tomorrow's return?<br/>"
            "<b>Lag = 0:</b> Do probability and return move together on the same day?<br/>"
            "<b>Lag = +1:</b> Does yesterday's return predict today's probability?<br/><br/>"
            "If the peak correlation occurs at a negative lag, prediction markets lead equity markets — "
            "suggesting they contain information not yet priced into stocks.",
            ParagraphStyle("ll", fontSize=10, fontName="Helvetica",
                          textColor=DARK, leading=16, leftIndent=8)
        )
    ]]
    ll_box = Table(ll_data, colWidths=[6.5*inch])
    ll_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#F0F7FF")),
        ("BOX",           (0,0),(-1,-1), 1, ACCENT),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
    ]))
    story.append(ll_box)
    story.append(Spacer(1, 0.12*inch))

    story.append(Paragraph("Tech Stack", S["sub_header"]))
    tech_data = [
        ["Layer",           "Tool",                   "Purpose"],
        ["Data Sources",    "Manifold Markets API",    "Prediction market probabilities (fully public)"],
        ["Data Sources",    "Polymarket Gamma API",    "Additional prediction market snapshots"],
        ["Data Sources",    "yfinance",                "SPY, QQQ, VIX, TLT, GLD, BTC-USD daily OHLCV"],
        ["ETL",             "Python (requests, pandas)","Fetch → clean → load with incremental upserts"],
        ["Storage",         "PostgreSQL 16",           "Normalized schema with indexes and views"],
        ["Analysis",        "Python (pandas, numpy)",  "Lead/lag correlation, quintile bucketing"],
        ["Export",          "SQLAlchemy + CSV",        "Tableau-ready exports from PostgreSQL views"],
        ["Audit",           "etl_runs table",          "Full pipeline run log with row counts and status"],
    ]
    tt = Table(tech_data, colWidths=[1.1*inch, 1.7*inch, 3.7*inch])
    tt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ACCENT),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ("ALIGN",         (0,0),(-1,-1), "LEFT"),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [LIGHT, colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
    ]))
    story.append(tt)

    # ── SECTION 5: Key Takeaways ──────────────────────────────────────────────
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("Section 5 — Key Takeaways", S["section_header"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 0.08*inch))

    takeaways = [
        ("<b>Prediction markets are an underutilized data source in quantitative finance.</b> "
         "They aggregate crowd intelligence on macro events — Fed decisions, recession odds, "
         "Bitcoin levels — into a single probability updated in real time.", BLUE),
        ("<b>The pipeline is designed to run incrementally every day.</b> Each ETL run only "
         "inserts new rows (ON CONFLICT DO NOTHING), and every run is logged to the etl_runs "
         "audit table with row counts and status.", GREEN),
        ("<b>The database architecture mirrors production data engineering practice.</b> "
         "Normalized tables, foreign keys, indexes, and views separate storage from "
         "presentation — the same pattern used by quantitative research teams.", ACCENT),
        ("<b>Lead/lag correlation is the right tool for this question.</b> Simple same-day "
         "correlation conflates causation with coincidence. Testing at -10 to +10 day offsets "
         "reveals the temporal structure of the relationship.", GOLD),
        ("<b>Adding a Kalshi API key unlocks higher-liquidity markets.</b> Kalshi has deeper "
         "order books on Fed rate decisions than Manifold — the pipeline supports it with a "
         "single environment variable addition.", PURPLE),
    ]

    for text, color in takeaways:
        row = Table([[Paragraph(text, S["body"])]], colWidths=[6.5*inch])
        row.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LINEBEFORE",    (0,0),(0,-1),  3, color),
            ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#FAFAFA")),
        ]))
        story.append(row)
        story.append(Spacer(1, 0.05*inch))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        f"Generated {date.today().strftime('%B %d, %Y')} · "
        "Data: Manifold Markets API, Polymarket API, Yahoo Finance via yfinance · "
        "Not financial advice — for educational and research purposes only.",
        S["disclaimer"]
    ))

    doc.build(story)
    print(f"PDF saved to: {OUTPUT}")


if __name__ == "__main__":
    build_pdf()
