"""
Backtest CLI — validates signals on historical Schwab data.

Usage:
  python scripts/backtest.py --symbols AAPL TSLA --days 30
  python scripts/backtest.py --symbols NVDA --signal orb --days 10
  python scripts/backtest.py --symbols AAPL MSFT NVDA --signal vwap --days 60

Signals: momentum (default), vwap, orb
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from schwab.auth.oauth import SchwabAuth
from schwab.client.market_data import MarketDataClient
from schwab.backtest.engine import BacktestEngine
from schwab.backtest.signals import momentum_breakout, vwap_pullback, orb_breakout

SIGNALS = {
    "momentum": momentum_breakout,
    "vwap": vwap_pullback,
    "orb": orb_breakout,
}


def main():
    parser = argparse.ArgumentParser(description="Backtest signals on Schwab data")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--signal", choices=list(SIGNALS.keys()), default="momentum")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--stop", type=float, default=1.0, help="Stop loss %%")
    parser.add_argument("--tp", type=float, default=2.0, help="Take profit %%")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    auth = SchwabAuth()
    mdc = MarketDataClient(auth)
    engine = BacktestEngine(stop_loss_pct=args.stop, take_profit_pct=args.tp)
    signal_fn = SIGNALS[args.signal]

    results = []
    for symbol in args.symbols:
        logger.info(f"Fetching {args.days}d of 5-min bars for {symbol}...")
        try:
            bars = mdc.get_candles(
                symbol,
                period_type="day",
                period=args.days,
                frequency_type="minute",
                frequency=5,
            )
            result = engine.run(symbol, bars, signal_fn)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed {symbol}: {e}")

    if args.as_json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(f"\n=== Backtest: {args.signal} signal, {args.days}d, "
              f"SL {args.stop}% / TP {args.tp}% ===\n")
        for r in results:
            print(r.summary)
        if results:
            avg_win = sum(r.win_rate for r in results if r.n_trades > 0) / max(
                1, sum(1 for r in results if r.n_trades > 0)
            )
            print(f"\nAvg win rate across {len(results)} symbols: {avg_win:.1%}")


if __name__ == "__main__":
    main()
