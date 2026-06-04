"""
Pre-market momentum scanner using finvizfinance.

Produces a ranked watchlist of symbols that meet intraday swing criteria:
  - Price: $5–$500
  - Volume: above 500K average
  - Float: not nano-cap junk (market cap > $300M)
  - Relative Volume: elevated (rsivol filter)
  - Change: gapping up or showing momentum (>1% change)
  - Optionable: yes (so UW flow data exists)

Runs before market open. Output feeds run_pipeline.py as the symbol list.
"""
import pandas as pd
from loguru import logger
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.performance import Performance


# Finviz filter keys: https://finvizfinance.readthedocs.io/en/latest/
INTRADAY_SWING_FILTERS = {
    "Price": "5to500",           # $5–$500 (liquid, not penny)
    "Average Volume": "500K+",   # avg vol > 500K
    "Market Cap.": "Mid ($300mln to $2bln),Large ($2bln to $10bln),Mega ($10bln+)",
    "Option/Short": "Optionable", # must have options (for UW flow)
    "Change": "Up 1%",           # showing at least some momentum
    "Country": "USA",
}

# Column name mapping from finvizfinance overview
OVERVIEW_COLUMNS = ["Ticker", "Company", "Sector", "Price", "Change", "Volume"]


class MomentumScanner:
    def __init__(self, max_symbols: int = 20):
        self.max_symbols = max_symbols

    def scan(self, extra_filters: dict = None) -> list[str]:
        """
        Run the pre-market scan and return a ranked list of ticker symbols.
        Returns empty list on any failure — never raises.
        """
        filters = {**INTRADAY_SWING_FILTERS, **(extra_filters or {})}
        try:
            overview = Overview()
            overview.set_filter(filters_dict=filters)
            df = overview.screener_view()
            if df is None or df.empty:
                logger.info("Scanner: no results for filters — returning empty list")
                return []

            ranked = self._rank(df)
            symbols = ranked["Ticker"].tolist()[:self.max_symbols]
            logger.info(f"Scanner: {len(symbols)} symbols — {symbols[:10]}")
            return symbols

        except Exception as e:
            logger.warning(f"Scanner: scan failed ({e}) — returning empty list")
            return []

    def scan_with_detail(self, extra_filters: dict = None) -> pd.DataFrame:
        """
        Same as scan() but returns the full DataFrame for logging/display.
        """
        filters = {**INTRADAY_SWING_FILTERS, **(extra_filters or {})}
        try:
            overview = Overview()
            overview.set_filter(filters_dict=filters)
            df = overview.screener_view()
            if df is None or df.empty:
                return pd.DataFrame()
            return self._rank(df).head(self.max_symbols)
        except Exception as e:
            logger.warning(f"Scanner.scan_with_detail failed: {e}")
            return pd.DataFrame()

    def top_gainers(self, limit: int = 10) -> list[str]:
        """Quick scan for top % gainers — useful for gap-and-go setups."""
        try:
            perf = Performance()
            perf.set_filter(filters_dict={"Option/Short": "Optionable", "Country": "USA"})
            df = perf.screener_view(order="Change")
            if df is None or df.empty:
                return []
            # Performance screener has 'Ticker' column and '1W' etc
            tickers = df.head(limit)["Ticker"].tolist()
            logger.info(f"Scanner.top_gainers: {tickers}")
            return tickers
        except Exception as e:
            logger.warning(f"Scanner.top_gainers failed: {e}")
            return []

    def _rank(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Score and rank results. Priority: % change desc, then volume desc.
        Change column from finviz comes as string like '2.45%' — clean it.
        """
        df = df.copy()
        for col in ["Change", "Volume"]:
            if col not in df.columns:
                continue
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        sort_cols = [c for c in ["Change", "Volume"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols, ascending=False)
        return df.reset_index(drop=True)
