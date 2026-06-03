"""RiskAgent — sizes each signal within account value + mandate constraints."""

from __future__ import annotations

from loguru import logger

from ..client import MarketDataClient
from ..safety import Mandate
from ._llm import ask_claude, extract_json

SYSTEM = (
    "You are a risk manager sizing intraday equity positions for a single retail "
    "trader with strict limits. For each signal you are given the account value, "
    "the mandate's max per-position dollar cap, the signal confidence, and the "
    "latest price. Return a JSON array; each item: "
    '{"symbol": str, "qty": int, "rationale": str}. '
    "Rules you MUST honor: qty*price must not exceed the max per-position cap; "
    "size DOWN for lower confidence; never exceed what the account can fund; "
    "qty is whole shares. When in doubt, size smaller. Output ONLY the JSON array."
)


class RiskAgent:
    def __init__(self, market_data: MarketDataClient | None = None):
        self.md = market_data or MarketDataClient()

    def _price(self, symbol: str) -> float:
        try:
            q = self.md.get_quote(symbol)
            # Schwab quote shapes vary; probe the common last/mark fields.
            for path in (("quote", "lastPrice"), ("quote", "mark"), ("lastPrice",), ("mark",)):
                node = q
                for key in path:
                    node = (node or {}).get(key) if isinstance(node, dict) else None
                if isinstance(node, (int, float)) and node > 0:
                    return float(node)
        except Exception as e:  # noqa: BLE001
            logger.warning("price fetch failed for {}: {}", symbol, e)
        return 0.0

    def run(self, signals: list[dict], account_value: float, mandate: Mandate) -> list[dict]:
        if not signals:
            return []
        # Attach a current price to each signal for the model + the hard clamp.
        enriched_in = []
        for s in signals:
            price = self._price(s["symbol"])
            enriched_in.append({**s, "price": price})

        user = (
            f"Account value: ${account_value:,.2f}\n"
            f"Max per-position cap: ${mandate.max_position_usd:,.2f}\n"
            f"Daily loss limit: ${mandate.daily_loss_limit_usd:,.2f}\n\n"
            f"Signals (with latest price): {enriched_in}\n\n"
            "Size each position."
        )
        parsed = extract_json(ask_claude(SYSTEM, user))
        sizing = {}
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get("symbol"):
                    try:
                        sizing[str(item["symbol"]).upper()] = int(item.get("qty", 0))
                    except (TypeError, ValueError):
                        continue

        out = []
        for s in enriched_in:
            price = s["price"]
            qty = sizing.get(s["symbol"], 0)
            if price <= 0 or qty < 1:
                continue
            # HARD clamp regardless of what the model returned — never exceed the
            # mandate cap. This is belt-and-suspenders to the order guard.
            if mandate.max_position_usd > 0:
                max_qty = int(mandate.max_position_usd // price)
                qty = min(qty, max_qty)
            if qty < 1:
                continue
            out.append({**s, "qty": qty, "estimated_cost": round(qty * price, 2)})
        logger.info("risk: {} sized signal(s)", len(out))
        return out
