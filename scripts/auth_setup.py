"""
One-time OAuth setup wizard.

Usage:
    python scripts/auth_setup.py

Prints the Schwab authorize URL, waits for you to log in and paste the URL you
were redirected to (the browser will likely show "can't be reached" at
https://127.0.0.1 — that's expected; copy the full address-bar URL), exchanges
the code for tokens, persists them to .env, and prints your account numbers so
you can set SCHWAB_ACCOUNT_HASH.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from schwab.auth import SchwabAuth  # noqa: E402
from schwab.client import AccountsClient  # noqa: E402


def main() -> int:
    auth = SchwabAuth()
    print("\n1) Open this URL, log in, and authorize the app:\n")
    print("   " + auth.get_auth_url() + "\n")
    print("2) Your browser will redirect to https://127.0.0.1?code=...  ")
    print("   It may show 'this site can't be reached' — that is fine.")
    print("   Copy the FULL URL from the address bar.\n")
    redirected = input("3) Paste the full redirected URL here: ").strip()
    if not redirected:
        print("No URL provided. Aborting.")
        return 1

    auth.exchange_code(redirected)
    print("\nAuth successful. Tokens saved to .env.\n")

    try:
        accts = AccountsClient(auth).get_account_numbers()
        print("Your accounts (set SCHWAB_ACCOUNT_HASH to the hashValue you trade):\n")
        for a in accts:
            print(f"   accountNumber={a.get('accountNumber')}  hashValue={a.get('hashValue')}")
    except Exception as e:  # noqa: BLE001
        print(f"(Could not fetch account numbers automatically: {e})")
        print("Run scripts/account_status.py after setting tokens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
