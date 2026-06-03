"""Account info, balances, positions."""

from __future__ import annotations

from loguru import logger

from .base import SchwabClient


class AccountsClient(SchwabClient):
    def get_account_numbers(self) -> list[dict]:
        """GET /accounts/accountNumbers — maps plain account numbers to the
        hashed values used in every other account/order path."""
        return self.get("/accounts/accountNumbers") or []

    def get_account(self, account_hash: str) -> dict:
        """GET /accounts/{hash}?fields=positions — full account incl. positions."""
        return self.get(f"/accounts/{account_hash}", params={"fields": "positions"}) or {}

    def get_positions(self, account_hash: str) -> list[dict]:
        acct = self.get_account(account_hash)
        sa = (acct or {}).get("securitiesAccount", {})
        return sa.get("positions", []) or []

    def get_account_value(self, account_hash: str) -> float:
        """Liquidation value of the account (for position sizing). Falls back
        across the common Schwab balance field names; 0.0 if none present."""
        acct = self.get_account(account_hash)
        sa = (acct or {}).get("securitiesAccount", {})
        bal = sa.get("currentBalances", {}) or sa.get("initialBalances", {}) or {}
        for key in ("liquidationValue", "equity", "cashBalance", "availableFunds"):
            val = bal.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
        logger.warning("Could not read account value from balances; returning 0.0")
        return 0.0
