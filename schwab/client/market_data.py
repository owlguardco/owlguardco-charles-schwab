"""Quotes, candles, movers."""

from __future__ import annotations

from .base import SchwabClient


class MarketDataClient(SchwabClient):
    def get_quote(self, symbol: str) -> dict:
        """GET /marketdata/v1/quotes?symbols=SYM — returns the quote block for
        the symbol (Schwab keys the response by symbol)."""
        data = self.get("/marketdata/v1/quotes", params={"symbols": symbol}) or {}
        return data.get(symbol, data)

    def get_candles(
        self,
        symbol: str,
        period_type: str = "day",
        period: int = 1,
        frequency_type: str = "minute",
        frequency: int = 5,
    ) -> list[dict]:
        """GET /marketdata/v1/pricehistory — OHLCV candles. Returns the
        `candles` array (each: {open, high, low, close, volume, datetime})."""
        params = {
            "symbol": symbol,
            "periodType": period_type,
            "period": period,
            "frequencyType": frequency_type,
            "frequency": frequency,
        }
        data = self.get("/marketdata/v1/pricehistory", params=params) or {}
        return data.get("candles", []) or []

    def get_movers(self, index: str = "$DJI") -> list[dict]:
        """GET /marketdata/v1/movers/{index} — top movers for an index."""
        data = self.get(f"/marketdata/v1/movers/{index}") or {}
        return data.get("screeners", data.get("movers", [])) or []
