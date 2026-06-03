"""
ExecutionAgent — the only component that places orders. For each sized signal it
runs the mandatory pre-flight, submits a MARKET order on pass, journals the
outcome, and alerts Discord. ANY unexpected exception trips the kill switch so a
broken run cannot keep firing orders.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from ..client import OrdersClient
from ..discord import DiscordNotifier
from ..safety import KillSwitch, Mandate, OrderGuard

TRADE_LOG = Path(__file__).resolve().parents[1] / "data" / "trade_log.csv"
_FIELDS = ["timestamp", "symbol", "side", "qty", "price", "estimated_cost",
           "confidence", "result", "order_id", "detail"]

# direction -> order instruction. SHORT signals sell-to-open; on a cash/margin
# retail account a SHORT the trader doesn't hold may be rejected by the broker —
# that rejection surfaces in the journal rather than being silently swallowed.
_SIDE = {"LONG": "BUY", "SHORT": "SELL"}


class ExecutionAgent:
    def _journal(self, row: dict) -> None:
        TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
        new = not TRADE_LOG.exists()
        with TRADE_LOG.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in _FIELDS})

    def run(
        self,
        sized_signals: list[dict],
        account_hash: str,
        orders_client: OrdersClient,
        order_guard: OrderGuard,
        kill_switch: KillSwitch,
        mandate: Mandate,
        notifier: DiscordNotifier,
    ) -> list[dict]:
        results = []
        for sig in sized_signals:
            symbol = sig["symbol"]
            qty = int(sig["qty"])
            price = float(sig.get("price", 0))
            side = _SIDE.get(sig.get("direction", ""), "")
            ts = datetime.now(timezone.utc).isoformat()
            base = {
                "timestamp": ts, "symbol": symbol, "side": side, "qty": qty,
                "price": price, "estimated_cost": sig.get("estimated_cost", ""),
                "confidence": sig.get("confidence", ""),
            }

            ok, reason = order_guard.pre_flight(symbol, qty, price, side, mandate, kill_switch)
            if not ok:
                logger.warning("BLOCKED {} {} x{}: {}", side, symbol, qty, reason)
                self._journal({**base, "result": "blocked", "detail": reason})
                notifier.send("⛔ Order blocked", f"{side} {symbol} x{qty}: {reason}", color=0xFFA500)
                results.append({**sig, "result": "blocked", "detail": reason})
                continue

            try:
                order = orders_client.build_market_order(symbol, qty, side)
                placed = orders_client.place_order(account_hash, order)
                oid = placed.get("order_id") or ""
                self._journal({**base, "result": "submitted", "order_id": oid, "detail": ""})
                notifier.send(
                    "✅ Order submitted",
                    f"{side} {symbol} x{qty} @ ~${price:,.2f} (conf {sig.get('confidence')}) "
                    f"order_id={oid}",
                    color=0x00FF00,
                )
                results.append({**sig, "result": "submitted", "order_id": oid})
                logger.info("submitted {} {} x{} order_id={}", side, symbol, qty, oid)
            except Exception as e:  # noqa: BLE001 — a failure here halts everything
                detail = str(e)
                logger.critical("execution error on {} {} x{}: {}", side, symbol, qty, detail)
                self._journal({**base, "result": "error", "detail": detail})
                results.append({**sig, "result": "error", "detail": detail})
                kill_switch.activate(f"execution error on {symbol}: {detail}")
                notifier.send(
                    "🛑 Execution error — kill switch tripped",
                    f"{side} {symbol} x{qty} failed: {detail}",
                    color=0xFF0000,
                )
                break  # stop the run; a tripped kill switch blocks the rest anyway
        return results
