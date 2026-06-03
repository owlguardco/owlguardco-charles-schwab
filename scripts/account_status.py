"""
Print account balances + open positions.

Usage:
    python scripts/account_status.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from schwab.client import AccountsClient  # noqa: E402


def main() -> int:
    client = AccountsClient()
    account_hash = os.environ.get("SCHWAB_ACCOUNT_HASH", "")
    if not account_hash:
        print("SCHWAB_ACCOUNT_HASH not set. Listing account numbers instead:\n")
        for a in client.get_account_numbers():
            print(f"   accountNumber={a.get('accountNumber')}  hashValue={a.get('hashValue')}")
        print("\nSet SCHWAB_ACCOUNT_HASH=<hashValue> in .env, then re-run.")
        return 1

    value = client.get_account_value(account_hash)
    positions = client.get_positions(account_hash)
    print(f"\nAccount value: ${value:,.2f}")
    print(f"Open positions: {len(positions)}")
    for p in positions:
        instr = p.get("instrument", {})
        qty = p.get("longQuantity", 0) - p.get("shortQuantity", 0)
        print(f"   {instr.get('symbol', '?'):8} qty={qty:>8}  mktValue=${p.get('marketValue', 0):,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
