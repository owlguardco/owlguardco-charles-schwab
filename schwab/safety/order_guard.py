"""
OrderGuard — the mandatory pre-flight gate. EVERY order passes through
pre_flight() before submission. Fails closed on every check.

Order of checks (cheapest / most-decisive first):
  1. kill switch active        -> block
  2. invalid side / qty / price -> block
  3. symbol not in mandate allowlist -> block
  4. position size exceeds mandate cap -> block
  5. duplicate (same symbol+side already submitted this run) -> block
"""

from __future__ import annotations

from loguru import logger

from .kill_switch import KillSwitch
from .mandate import Mandate


class OrderGuard:
    def __init__(self):
        # symbols+side already cleared this run, for duplicate detection.
        self._submitted: set[tuple[str, str]] = set()

    def reset(self) -> None:
        self._submitted.clear()

    def pre_flight(
        self,
        symbol: str,
        qty: int,
        price: float,
        side: str,
        mandate: Mandate,
        kill_switch: KillSwitch,
    ) -> tuple[bool, str]:
        symbol = (symbol or "").upper()
        side = (side or "").upper()

        if kill_switch.is_active():
            return False, f"kill switch active: {kill_switch.reason() or 'no reason given'}"
        if side not in ("BUY", "SELL"):
            return False, f"invalid side {side!r} (must be BUY/SELL)"
        if qty < 1:
            return False, f"quantity {qty} < 1"
        if price <= 0:
            return False, f"non-positive price {price}"
        if not mandate.allows_symbol(symbol):
            return False, f"{symbol} not in mandate allowlist"
        if not mandate.allows_size(qty, price):
            return (
                False,
                f"position ${qty * price:,.2f} exceeds mandate cap "
                f"${mandate.max_position_usd:,.2f}",
            )
        key = (symbol, side)
        if key in self._submitted:
            return False, f"duplicate {side} {symbol} already submitted this run"

        self._submitted.add(key)
        logger.info("pre-flight OK: {} {} x{} @ ~{}", side, symbol, qty, price)
        return True, "ok"
