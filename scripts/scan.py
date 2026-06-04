"""
Pre-market scanner CLI.

Usage:
  python scripts/scan.py               # run default momentum scan, print tickers
  python scripts/scan.py --detail      # print full table with price/change/volume
  python scripts/scan.py --gainers     # top % gainers only
  python scripts/scan.py --max 30      # override max symbols (default 20)
  python scripts/scan.py --run         # scan then immediately run the pipeline
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from schwab.screener.scanner import MomentumScanner


def main():
    parser = argparse.ArgumentParser(description="Pre-market momentum scanner")
    parser.add_argument("--detail", action="store_true", help="Print full table")
    parser.add_argument("--gainers", action="store_true", help="Top gainers scan")
    parser.add_argument("--max", type=int, default=20, dest="max_symbols")
    parser.add_argument("--run", action="store_true", help="Run pipeline after scan")
    args = parser.parse_args()

    scanner = MomentumScanner(max_symbols=args.max_symbols)

    if args.gainers:
        symbols = scanner.top_gainers(limit=args.max_symbols)
        print("Top Gainers:", symbols)
    elif args.detail:
        df = scanner.scan_with_detail()
        if df.empty:
            print("No results.")
        else:
            print(df.to_string(index=False))
            print(f"\nSymbols: {df['Ticker'].tolist()}")
    else:
        symbols = scanner.scan()
        print(" ".join(symbols))

    if args.run and not args.gainers and not args.detail:
        if not symbols:
            logger.warning("No symbols from scan — skipping pipeline run")
            return
        from schwab.pipeline.runner import TradingPipeline
        pipeline = TradingPipeline()
        pipeline.run(symbols)


if __name__ == "__main__":
    main()
