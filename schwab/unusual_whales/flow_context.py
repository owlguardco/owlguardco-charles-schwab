"""
Builds a flow context summary for each symbol — used by ResearchAgent
to enrich the SignalAgent prompt with smart money positioning.
"""
import json
from loguru import logger
from schwab.unusual_whales.client import UnusualWhalesClient, UnusualWhalesError


def get_flow_context(
    client: UnusualWhalesClient | None,
    symbols: list[str],
) -> dict[str, str]:
    """
    Returns {symbol: flow_summary_text} for each symbol.
    Empty string if UW unavailable or no data.
    Never raises.
    """
    if client is None:
        return {s: "" for s in symbols}

    results = {}
    for symbol in symbols:
        try:
            parts = []

            # Options flow for this ticker
            alerts = client.flow_alerts(ticker=symbol, min_premium=25_000, limit=10)
            if alerts:
                parts.append(f"OPTIONS FLOW ({len(alerts)} alerts): " +
                    json.dumps(alerts[:3], default=str)[:500])

            # Dark pool
            dp = client.darkpool_ticker(symbol, limit=5)
            if dp:
                parts.append(f"DARK POOL ({len(dp)} prints): " +
                    json.dumps(dp[:2], default=str)[:300])

            results[symbol] = "\n".join(parts) if parts else ""

        except UnusualWhalesError as e:
            logger.warning(f"UW flow_context failed for {symbol}: {e}")
            results[symbol] = ""

    return results


def get_market_flow_summary(client: UnusualWhalesClient | None) -> str:
    """
    One-paragraph market-wide flow summary for the SignalAgent prompt.
    Covers: market tide direction, top OI change tickers, macro calendar.
    """
    if client is None:
        return ""

    parts = []
    try:
        tide = client.market_tide()
        if tide:
            parts.append(f"MARKET TIDE: {json.dumps(tide, default=str)[:300]}")
    except UnusualWhalesError:
        pass

    try:
        oi = client.oi_change(limit=5)
        if oi:
            tickers = [x.get("ticker", x.get("symbol", "?")) for x in oi[:5]]
            parts.append(f"TOP OI CHANGE: {tickers}")
    except UnusualWhalesError:
        pass

    try:
        cal = client.economic_calendar()
        if cal:
            parts.append(f"MACRO CALENDAR: {json.dumps(cal[:2], default=str)[:200]}")
    except UnusualWhalesError:
        pass

    return "\n".join(parts)
