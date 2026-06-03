"""
Interactive helper to capture the current Fincept MCP endpoint + token.

Run after (re)launching FinceptTerminal:
  python scripts/fincept_discover.py

Find the values in Fincept: Settings -> Developer -> MCP Bridge
(endpoint http://127.0.0.1:XXXXX and a UUID token).
"""

import re
import sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def update_env(key: str, value: str) -> None:
    """Write/update a single key in .env without touching other keys."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n")


def main() -> int:
    print("Fincept Terminal MCP Bridge Discovery")
    print("======================================\n")
    print("In FinceptTerminal: Settings -> Developer -> MCP Bridge")
    print("Copy the endpoint and token shown there.\n")

    endpoint = input("Endpoint (e.g. http://127.0.0.1:54321): ").strip()
    if not re.match(r"^http://127\.0\.0\.1:\d+$", endpoint):
        print(f"ERROR: expected http://127.0.0.1:PORT, got: {endpoint}")
        return 1

    token = input("Token (UUID): ").strip()
    if not re.match(r"^[0-9a-f-]{36}$", token, re.IGNORECASE):
        print(f"ERROR: expected a UUID, got: {token}")
        return 1

    update_env("FINCEPT_MCP_ENDPOINT", endpoint)
    update_env("FINCEPT_MCP_TOKEN", token)
    print(f"\nSaved to .env:\n  FINCEPT_MCP_ENDPOINT={endpoint}\n  FINCEPT_MCP_TOKEN={token}\n")

    # Quick connectivity check.
    import requests

    try:
        resp = requests.get(
            f"{endpoint}/tools",
            headers={"X-MCP-Token": token, "Connection": "close"},
            timeout=5,
        )
        if resp.ok:
            tools = resp.json()
            print(f"Connected. {len(tools)} tools available.")
        else:
            print(f"WARNING: got HTTP {resp.status_code}. Check the token.")
    except requests.exceptions.ConnectionError:
        print("WARNING: could not connect. Is FinceptTerminal running?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
