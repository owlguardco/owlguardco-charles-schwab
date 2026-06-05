"""
ResearchAgent — enriches watchlist symbols with market data, news, technicals,
and sentiment.

Data sources (priority order):
  1. FinceptTerminal MCP bridge (richer: live news, technicals, sentiment, geo)
  2. Schwab MarketDataClient (fallback when Fincept is not running)

Degrades gracefully: every Fincept call is wrapped, and Fincept availability
never breaks the run. The LLM call routes through the shared _llm helper so the
model stays env-configurable (ANTHROPIC_MODEL), consistent with the rest of the
system.
"""

from __future__ import annotations

import json

from loguru import logger

from ..client import MarketDataClient
from ..fincept.client import FinceptMCPClient, FinceptMCPError
from ..fincept.config import FinceptConfig
from ._llm import ask_claude

SYSTEM = (
    "You are an intraday equity research analyst for a single retail trader. "
    "Describe what the data shows; do not give advice or guarantees. If data is "
    "thin or missing, say so plainly. Never invent figures."
)


class ResearchAgent:
    def __init__(self, market_data_client: MarketDataClient | None = None):
        self.mdc = market_data_client or MarketDataClient()
        self._fincept: FinceptMCPClient | None = self._try_connect_fincept()
        self._uw: "UnusualWhalesClient | None" = self._try_connect_uw()

    def _try_connect_fincept(self) -> FinceptMCPClient | None:
        cfg = FinceptConfig()
        if not cfg.is_configured():
            logger.info("ResearchAgent: Fincept not configured — using Schwab data only")
            return None
        try:
            client = FinceptMCPClient(FinceptConfig.from_env())
            if client.ping():
                logger.info("ResearchAgent: Fincept MCP bridge connected")
                return client
            logger.warning("ResearchAgent: Fincept configured but unreachable — Schwab only")
            return None
        except Exception as e:  # noqa: BLE001 — Fincept must never break startup
            logger.warning("ResearchAgent: Fincept init failed ({}) — Schwab only", e)
            return None

    def _try_connect_uw(self) -> "UnusualWhalesClient | None":
        from schwab.unusual_whales.client import UnusualWhalesClient, UnusualWhalesError
        import os
        if not os.environ.get("UW_API_KEY"):
            logger.info("ResearchAgent: UW_API_KEY not set — skipping options flow")
            return None
        try:
            client = UnusualWhalesClient()
            if client.ping():
                logger.info("ResearchAgent: Unusual Whales connected")
                return client
            logger.warning("ResearchAgent: UW ping failed — skipping options flow")
            return None
        except Exception as e:
            logger.warning(f"ResearchAgent: UW init failed ({e})")
            return None

    def run(self, symbols: list[str]) -> dict:
        results: dict[str, str] = {}
        for symbol in symbols:
            symbol = symbol.upper()
            try:
                ctx = self._gather_context(symbol)
                results[symbol] = self._summarize(symbol, ctx)
            except Exception as e:  # noqa: BLE001
                logger.error("ResearchAgent: error on {}: {}", symbol, e)
                results[symbol] = f"Research failed: {e}"
        return results

    def _gather_context(self, symbol: str) -> dict:
        ctx = {"symbol": symbol, "source": "schwab"}
        if self._fincept:
            ctx["source"] = "fincept"
            try:
                ctx["quote"] = self._fincept.get_quote(symbol)
            except FinceptMCPError as e:
                logger.warning("Fincept get_quote failed for {}: {}", symbol, e)
                ctx["quote"] = self._schwab_quote_fallback(symbol)
            try:
                ctx["history"] = self._fincept.get_history(symbol, interval="5m", period="1d")
            except FinceptMCPError as e:
                logger.warning("Fincept get_history failed for {}: {}", symbol, e)
                ctx["history"] = self._schwab_history_fallback(symbol)
            for key, fn in (
                ("technicals", self._fincept.get_equity_technicals),
                ("sentiment", self._fincept.get_equity_sentiment),
            ):
                try:
                    ctx[key] = fn(symbol)
                except FinceptMCPError as e:
                    logger.warning("Fincept {} failed for {}: {}", key, symbol, e)
            try:
                ctx["news"] = self._fincept.get_news(symbol=symbol, limit=5)
            except FinceptMCPError as e:
                logger.warning("Fincept news failed for {}: {}", symbol, e)
        else:
            ctx["quote"] = self._schwab_quote_fallback(symbol)
            ctx["history"] = self._schwab_history_fallback(symbol)

        # Options flow (Unusual Whales)
        if self._uw:
            from schwab.unusual_whales.flow_context import get_flow_context
            flow = get_flow_context(self._uw, [symbol])
            ctx["options_flow"] = flow.get(symbol, "")

        # Free options chain (yfinance) — used when UW not configured
        if not self._uw:
            try:
                from schwab.options.chain import get_chain_snapshot
                options = get_chain_snapshot(symbol)
                if not options.get("error"):
                    ctx["options_chain"] = {
                        "put_call_ratio": options.get("put_call_ratio"),
                        "unusual_volume": options.get("unusual_volume", [])[:3],
                        "top_call_oi_strike": options.get("top_call_oi", [{}])[0].get("strike"),
                        "top_put_oi_strike": options.get("top_put_oi", [{}])[0].get("strike"),
                    }
            except Exception as e:
                logger.warning(f"yfinance options failed for {symbol}: {e}")
        return ctx

    def _schwab_quote_fallback(self, symbol: str) -> dict:
        try:
            return self.mdc.get_quote(symbol)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def _schwab_history_fallback(self, symbol: str) -> dict:
        try:
            bars = self.mdc.get_candles(symbol)
            return {"candles": bars[-20:] if len(bars) > 20 else bars}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def _summarize(self, symbol: str, ctx: dict) -> str:
        user = (
            f"Analyze this data for {symbol} and return, concisely (max ~150 words):\n"
            "1. Price action summary (trend, key levels, notable moves)\n"
            "2. Volume / momentum signals\n"
            "3. News sentiment (if available)\n"
            "4. Technical read (bullish / bearish / neutral)\n"
            "5. Is there an intraday swing setup worth investigating? (yes/no + one sentence)\n\n"
            f"Data:\n{json.dumps(ctx, indent=2, default=str)[:6000]}"
        )
        return ask_claude(SYSTEM, user) or "no research produced"
