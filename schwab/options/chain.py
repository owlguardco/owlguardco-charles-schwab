"""
Free options chain data via yfinance.

Used as a fallback when UW_API_KEY is not set.
Surfaces:
  - Put/call ratio (OI-based)
  - Highest OI strikes (calls + puts)
  - Unusual volume: strikes where volume > 2x open interest
  - Near-term expiry focus (next 2 expirations)

Never raises — returns empty dict on any failure.
"""
from __future__ import annotations

import datetime
from loguru import logger


def get_chain_snapshot(symbol: str, max_expirations: int = 2) -> dict:
    """
    Fetch options chain for a symbol and return a structured snapshot.

    Returns:
    {
        symbol: str,
        expiries: [str, ...],
        put_call_ratio: float,
        top_call_oi: [{strike, oi, volume, expiry}, ...],
        top_put_oi: [{strike, oi, volume, expiry}, ...],
        unusual_volume: [{strike, type, volume, oi, ratio, expiry}, ...],
        error: str | None
    }
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"symbol": symbol, "error": "yfinance not installed"}

    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {"symbol": symbol, "error": "no options data available"}

        # Focus on next N expirations
        target_expiries = list(expirations[:max_expirations])

        all_calls = []
        all_puts = []

        for expiry in target_expiries:
            try:
                chain = ticker.option_chain(expiry)
                calls = chain.calls.copy()
                puts = chain.puts.copy()
                calls["expiry"] = expiry
                puts["expiry"] = expiry
                all_calls.append(calls)
                all_puts.append(puts)
            except Exception as e:
                logger.warning(f"options chain fetch failed for {symbol} {expiry}: {e}")
                continue

        if not all_calls and not all_puts:
            return {"symbol": symbol, "error": "chain fetch failed for all expiries"}

        import pandas as pd
        calls_df = pd.concat(all_calls, ignore_index=True) if all_calls else pd.DataFrame()
        puts_df = pd.concat(all_puts, ignore_index=True) if all_puts else pd.DataFrame()

        # Put/call ratio by OI
        total_call_oi = calls_df["openInterest"].fillna(0).sum() if not calls_df.empty else 0
        total_put_oi = puts_df["openInterest"].fillna(0).sum() if not puts_df.empty else 0
        pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 0.0

        # Top OI strikes
        def top_oi(df, n=5):
            if df.empty:
                return []
            df = df.copy()
            df["openInterest"] = df["openInterest"].fillna(0)
            df["volume"] = df["volume"].fillna(0)
            top = df.nlargest(n, "openInterest")
            return [
                {
                    "strike": float(row["strike"]),
                    "oi": int(row["openInterest"]),
                    "volume": int(row["volume"]),
                    "expiry": row["expiry"],
                }
                for _, row in top.iterrows()
            ]

        # Unusual volume: volume > 2x OI and volume > 100
        def unusual_vol(df, side, min_volume=100, ratio_threshold=2.0):
            if df.empty:
                return []
            df = df.copy()
            df["openInterest"] = df["openInterest"].fillna(0)
            df["volume"] = df["volume"].fillna(0)
            mask = (df["volume"] > min_volume) & (
                df["volume"] > df["openInterest"] * ratio_threshold
            )
            unusual = df[mask].copy()
            if unusual.empty:
                return []
            unusual["vol_oi_ratio"] = (
                unusual["volume"] / unusual["openInterest"].replace(0, 1)
            ).round(1)
            unusual = unusual.nlargest(5, "vol_oi_ratio")
            return [
                {
                    "strike": float(row["strike"]),
                    "type": side,
                    "volume": int(row["volume"]),
                    "oi": int(row["openInterest"]),
                    "ratio": float(row["vol_oi_ratio"]),
                    "expiry": row["expiry"],
                }
                for _, row in unusual.iterrows()
            ]

        top_calls = top_oi(calls_df)
        top_puts = top_oi(puts_df)
        unusual = unusual_vol(calls_df, "CALL") + unusual_vol(puts_df, "PUT")
        unusual.sort(key=lambda x: x["ratio"], reverse=True)

        return {
            "symbol": symbol,
            "expiries": target_expiries,
            "put_call_ratio": pcr,
            "top_call_oi": top_calls,
            "top_put_oi": top_puts,
            "unusual_volume": unusual[:10],
            "error": None,
        }

    except Exception as e:
        logger.warning(f"get_chain_snapshot failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


def get_market_flow_free(symbols: list[str]) -> dict:
    """
    Run chain snapshots for a list of symbols.
    Returns {symbol: snapshot_dict} for each.
    Aggregates unusual volume across all symbols for dashboard display.
    """
    results = {}
    all_unusual = []

    for sym in symbols[:10]:  # cap at 10 to avoid rate limits
        snap = get_chain_snapshot(sym)
        results[sym] = snap
        for item in snap.get("unusual_volume", []):
            item["symbol"] = sym
            all_unusual.append(item)

    all_unusual.sort(key=lambda x: x["ratio"], reverse=True)

    return {
        "by_symbol": results,
        "unusual_volume": all_unusual[:20],
        "source": "yfinance",
    }
