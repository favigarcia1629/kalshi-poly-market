"""
Main entry point — runs the full pipeline then exports CSVs for Tableau.

Usage:
    python run_etl.py           # full ETL + Tableau export
    python run_etl.py --stocks  # stocks only (fast, <10s)
    python run_etl.py --export  # export CSVs only (no API calls)
"""
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(__file__))

from etl.pipeline      import run_full_pipeline, run_stock_etl, _engine
from export_tableau    import export_all
from analysis.correlations import run_analysis


def main():
    args = sys.argv[1:]
    engine = _engine()

    if "--export" in args:
        print("[Mode] Export only")
        export_all()
        return

    if "--stocks" in args:
        print("[Mode] Stocks only")
        run_stock_etl(engine)
        export_all()
        return

    if "--analysis" in args:
        print("[Mode] Analysis only")
        run_analysis()
        return

    # Full pipeline
    print("=" * 60)
    print("  Prediction Markets ETL Pipeline")
    print("=" * 60)

    run_full_pipeline()

    print("\n" + "=" * 60)
    print("  Exporting CSVs for Tableau...")
    print("=" * 60)
    export_all()

    print("\n" + "=" * 60)
    print("  Running correlation analysis...")
    print("=" * 60)
    run_analysis()

    print("\nDone. Open Tableau Public Desktop to build your dashboard.")


if __name__ == "__main__":
    main()
