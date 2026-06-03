"""
CLI entry point for the trading pipeline.

Usage:
    python scripts/run_pipeline.py --symbols AAPL TSLA NVDA
    python scripts/run_pipeline.py            # uses MANDATE_SYMBOL_ALLOWLIST
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from loguru import logger  # noqa: E402

from schwab.pipeline import TradingPipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the OwlGuardCo Schwab trading pipeline.")
    ap.add_argument("--symbols", nargs="*", default=None,
                    help="Symbols to consider (default: MANDATE_SYMBOL_ALLOWLIST).")
    args = ap.parse_args()

    symbols = args.symbols
    if not symbols:
        raw = os.environ.get("MANDATE_SYMBOL_ALLOWLIST", "")
        symbols = [s.strip() for s in raw.split(",") if s.strip()]
    if not symbols:
        logger.error("No symbols given and MANDATE_SYMBOL_ALLOWLIST is empty.")
        return 1

    result = TradingPipeline().run(symbols)
    print("\n=== Run result ===")
    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
