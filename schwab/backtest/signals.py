"""
Reusable signal functions for backtesting.
Each function matches the signature:
  fn(close, high, low, volume) -> pd.Series[bool]

These mirror the logic the ResearchAgent prompts for — so backtesting
validates the same setups the system actually trades.
"""
import pandas as pd
import numpy as np


def momentum_breakout(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    lookback: int = 20,
    vol_multiplier: float = 1.5,
) -> pd.Series:
    """
    Enter when:
    - Price breaks above the N-bar high (momentum breakout)
    - Volume is X times the rolling average (confirmation)
    """
    rolling_high = high.shift(1).rolling(lookback).max()
    avg_vol = volume.rolling(lookback).mean()

    signal = (close > rolling_high) & (volume > avg_vol * vol_multiplier)
    return signal.fillna(False)


def vwap_pullback(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    vwap_window: int = 14,
    rsi_period: int = 14,
    rsi_oversold: float = 40.0,
) -> pd.Series:
    """
    Enter when:
    - Price is near VWAP (within 0.5%)
    - RSI is recovering from oversold territory
    Intraday pullback-to-VWAP long setup.
    """
    # Approximate VWAP as volume-weighted moving average
    typical = (high + low + close) / 3
    vwap = (typical * volume).rolling(vwap_window).sum() / volume.rolling(vwap_window).sum()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    near_vwap = (close - vwap).abs() / vwap < 0.005
    rsi_recovering = (rsi > rsi_oversold) & (rsi.shift(1) <= rsi_oversold)

    signal = near_vwap & rsi_recovering
    return signal.fillna(False)


def orb_breakout(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    opening_bars: int = 6,  # first 30 min on 5-min bars
) -> pd.Series:
    """
    Opening Range Breakout: enter when price exceeds the high of the
    first N bars of the session. Familiar from CI's B2 strategy.
    """
    # Mark first N bars as the opening range
    or_high = high.iloc[:opening_bars].max()
    signal = pd.Series(False, index=close.index)
    signal.iloc[opening_bars:] = close.iloc[opening_bars:] > or_high
    return signal.fillna(False)
