"""Place, cancel, list orders + a market-order builder."""

from __future__ import annotations

from loguru import logger

from .base import SchwabClient


class OrdersClient(SchwabClient):
    def place_order(self, account_hash: str, order_dict: dict) -> dict:
        """POST /accounts/{hash}/orders. Schwab returns the new order id in the
        Location header rather than the body; surface it when present."""
        resp = self.post(f"/accounts/{account_hash}/orders", json=order_dict)
        order_id = None
        loc = resp.headers.get("Location", "")
        if loc:
            order_id = loc.rstrip("/").rsplit("/", 1)[-1]
        body = resp.json() if resp.content else {}
        return {"order_id": order_id, "status_code": resp.status_code, "body": body}

    def cancel_order(self, account_hash: str, order_id: str) -> bool:
        """DELETE /accounts/{hash}/orders/{orderId}."""
        resp = self.delete(f"/accounts/{account_hash}/orders/{order_id}")
        return 200 <= resp.status_code < 300

    def get_orders(self, account_hash: str, from_entered_time: str | None = None) -> list[dict]:
        """GET /accounts/{hash}/orders."""
        params = {"fromEnteredTime": from_entered_time} if from_entered_time else None
        return self.get(f"/accounts/{account_hash}/orders", params=params) or []

    @staticmethod
    def build_market_order(symbol: str, quantity: int, instruction: str) -> dict:
        """A valid Schwab single-leg equity MARKET order, DAY, NORMAL session.
        instruction is 'BUY' or 'SELL'."""
        instruction = instruction.upper()
        if instruction not in ("BUY", "SELL"):
            raise ValueError(f"instruction must be BUY or SELL, got {instruction!r}")
        if quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {quantity}")
        return {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": quantity,
                    "instrument": {"symbol": symbol.upper(), "assetType": "EQUITY"},
                }
            ],
        }
