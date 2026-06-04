"""
Unusual Whales flow viewer.

Usage:
  python scripts/flow.py                    # market-wide flow + top OI
  python scripts/flow.py --ticker AAPL      # flow for specific ticker
  python scripts/flow.py --darkpool         # recent dark pool prints
  python scripts/flow.py --tide             # market tide only
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from schwab.unusual_whales.client import UnusualWhalesClient, UnusualWhalesError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str)
    parser.add_argument("--darkpool", action="store_true")
    parser.add_argument("--tide", action="store_true")
    parser.add_argument("--min-premium", type=int, default=50_000)
    args = parser.parse_args()

    try:
        client = UnusualWhalesClient()
    except EnvironmentError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    try:
        if args.ticker:
            print(f"=== Flow Alerts: {args.ticker} ===")
            alerts = client.flow_alerts(ticker=args.ticker, min_premium=args.min_premium, limit=20)
            print(json.dumps(alerts, indent=2, default=str))
            print(f"\n=== Dark Pool: {args.ticker} ===")
            dp = client.darkpool_ticker(args.ticker)
            print(json.dumps(dp, indent=2, default=str))

        elif args.darkpool:
            print("=== Recent Dark Pool Prints ===")
            dp = client.darkpool_recent(min_premium=args.min_premium)
            print(json.dumps(dp, indent=2, default=str))

        elif args.tide:
            print("=== Market Tide ===")
            tide = client.market_tide()
            print(json.dumps(tide, indent=2, default=str))

        else:
            print("=== Market Tide ===")
            print(json.dumps(client.market_tide(), indent=2, default=str))
            print("\n=== Top OI Change ===")
            print(json.dumps(client.oi_change(), indent=2, default=str))
            print("\n=== Top Net Impact ===")
            print(json.dumps(client.top_net_impact(), indent=2, default=str))
            print("\n=== Market-Wide Flow Alerts (min $50K) ===")
            print(json.dumps(client.flow_alerts(limit=20), indent=2, default=str))

    except UnusualWhalesError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
