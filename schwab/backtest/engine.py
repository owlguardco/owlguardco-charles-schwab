"""
Signal backtester using vectorbt.

Validates whether the Research→Signal pipeline's historical signals
would have been profitable on intraday 5-min bars.

Workflow:
  1. Fetch 5-min OHLCV for a symbol over N days (Schwab API)
  2. Apply the signal logic as a vectorized function over the price series
  3. Simulate entries at open of next bar after signal, exits at EOD or stop
  4. Report: win rate, avg R, max drawdown, Sharpe, total trades

Signal functions are simple callables:
  signal_fn(close: pd.Series, high: pd.Series, low: pd.Series, volume: pd.Series)
      -> pd.Series of bool (True = enter long that bar)
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from loguru import logger


@dataclass
class BacktestResult:
    symbol: str
    n_trades: int
    win_rate: float        # 0–1
    avg_return_pct: float  # mean trade return %
    max_drawdown_pct: float
    sharpe: float
    total_return_pct: float
    summary: str           # human-readable one-liner

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "n_trades": self.n_trades,
            "win_rate": round(self.win_rate, 3),
            "avg_return_pct": round(self.avg_return_pct, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 3),
            "sharpe": round(self.sharpe, 3),
            "total_return_pct": round(self.total_return_pct, 3),
        }


class BacktestEngine:
    def __init__(self, stop_loss_pct: float = 1.0, take_profit_pct: float = 2.0):
        """
        stop_loss_pct: exit if price drops this % below entry (default 1%)
        take_profit_pct: exit if price rises this % above entry (default 2%)
        Risk/reward of 1:2 — adjustable via env or constructor.
        """
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def run(
        self,
        symbol: str,
        bars: list[dict],
        signal_fn,
    ) -> BacktestResult:
        """
        Run backtest for one symbol.

        bars: list of OHLCV dicts from SchwabClient.get_candles()
              each: {datetime, open, high, low, close, volume}
        signal_fn: callable(close, high, low, volume) -> bool Series
        """
        if not bars or len(bars) < 10:
            return self._empty_result(symbol, "insufficient data")

        try:
            df = pd.DataFrame(bars)
            df = df.sort_values("datetime").reset_index(drop=True)

            close = df["close"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            volume = df["volume"].astype(float)

            # Get entry signals
            entries = signal_fn(close, high, low, volume)
            if not isinstance(entries, pd.Series):
                entries = pd.Series(entries, index=close.index)
            entries = entries.fillna(False).astype(bool)

            if entries.sum() == 0:
                return self._empty_result(symbol, "no signals generated")

            # Simulate trades: enter next bar after signal, exit on SL/TP/EOD
            returns = []
            i = 0
            while i < len(df) - 1:
                if entries.iloc[i]:
                    entry_price = close.iloc[i + 1]  # enter next bar open
                    sl = entry_price * (1 - self.stop_loss_pct / 100)
                    tp = entry_price * (1 + self.take_profit_pct / 100)

                    exit_price = entry_price
                    j = i + 2
                    while j < len(df):
                        bar_low = low.iloc[j]
                        bar_high = high.iloc[j]
                        bar_close = close.iloc[j]

                        if bar_low <= sl:
                            exit_price = sl
                            break
                        if bar_high >= tp:
                            exit_price = tp
                            break
                        # EOD: if next bar's datetime is a new day, exit at close
                        cur_day = str(df["datetime"].iloc[j])[:10]
                        prev_day = str(df["datetime"].iloc[j - 1])[:10]
                        if cur_day != prev_day:
                            exit_price = bar_close
                            break
                        j += 1
                    else:
                        exit_price = close.iloc[-1]

                    ret = (exit_price - entry_price) / entry_price * 100
                    returns.append(ret)
                    i = j  # skip to after this trade
                else:
                    i += 1

            if not returns:
                return self._empty_result(symbol, "no completed trades")

            arr = np.array(returns)
            wins = (arr > 0).sum()
            win_rate = wins / len(arr)
            avg_ret = arr.mean()
            total_ret = arr.sum()
            sharpe = (arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0.0

            # Max drawdown on equity curve
            equity = np.cumprod(1 + arr / 100)
            peak = np.maximum.accumulate(equity)
            dd = (equity - peak) / peak * 100
            max_dd = dd.min()

            summary = (
                f"{symbol}: {len(arr)} trades, "
                f"{win_rate:.0%} win rate, "
                f"avg {avg_ret:.2f}%, "
                f"max DD {max_dd:.2f}%, "
                f"Sharpe {sharpe:.2f}"
            )
            logger.info(f"Backtest: {summary}")

            return BacktestResult(
                symbol=symbol,
                n_trades=len(arr),
                win_rate=win_rate,
                avg_return_pct=avg_ret,
                max_drawdown_pct=max_dd,
                sharpe=sharpe,
                total_return_pct=total_ret,
                summary=summary,
            )

        except Exception as e:
            logger.error(f"BacktestEngine.run failed for {symbol}: {e}")
            return self._empty_result(symbol, str(e))

    def _empty_result(self, symbol: str, reason: str) -> BacktestResult:
        return BacktestResult(
            symbol=symbol, n_trades=0, win_rate=0.0,
            avg_return_pct=0.0, max_drawdown_pct=0.0,
            sharpe=0.0, total_return_pct=0.0,
            summary=f"{symbol}: no result ({reason})",
        )
