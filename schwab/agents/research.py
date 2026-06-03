"""ResearchAgent — per-symbol intraday read from candles + quote, summarized by Claude."""

from __future__ import annotations

from loguru import logger

from ..client import MarketDataClient
from ._llm import ask_claude

SYSTEM = (
    "You are an intraday equity research assistant for a single retail trader. "
    "Given recent 5-minute candles and the current quote for ONE US-listed stock, "
    "summarize price action, volume trend, and whether there is a plausible "
    "same-day intraday setup worth investigating. Be concise (4-6 sentences). "
    "Do not give financial advice or guarantees; describe what the data shows. "
    "If the data is thin or missing, say so plainly."
)


class ResearchAgent:
    def __init__(self, market_data: MarketDataClient | None = None):
        self.md = market_data or MarketDataClient()

    def run(self, symbols: list[str]) -> dict:
        out: dict[str, str] = {}
        for symbol in symbols:
            symbol = symbol.upper()
            try:
                candles = self.md.get_candles(symbol, period_type="day", period=1,
                                              frequency_type="minute", frequency=5)
                quote = self.md.get_quote(symbol)
            except Exception as e:  # noqa: BLE001
                logger.warning("research data fetch failed for {}: {}", symbol, e)
                out[symbol] = f"data unavailable ({e})"
                continue
            recent = candles[-40:] if candles else []
            user = (
                f"Symbol: {symbol}\n"
                f"Current quote: {quote}\n"
                f"Recent 5-min candles (last {len(recent)}): {recent}\n\n"
                "Summarize the intraday picture and whether there is a setup worth a closer look."
            )
            summary = ask_claude(SYSTEM, user) or "no research produced"
            out[symbol] = summary
            logger.info("research: {} -> {} chars", symbol, len(summary))
        return out
