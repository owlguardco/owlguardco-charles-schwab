"""
Unusual Whales REST API client.

Calls api.unusualwhales.com directly — no Node.js required.
Auth: Bearer token via UW_API_KEY env var.

Endpoints used (from unusual-whales/unusual-whales-official-mcp catalog):
  flow_alerts:     /api/option-trades/flow-alerts
  darkpool_recent: /api/darkpool/recent
  darkpool_ticker: /api/darkpool/{ticker}
  market_tide:     /api/market/market-tide
  oi_change:       /api/market/oi-change (top OI change tickers)
  top_net_impact:  /api/market/net-flow (top net premium tickers)
  uw_screener:     /api/screener/stocks
"""
import os
import requests
from loguru import logger


class UnusualWhalesError(Exception):
    pass


class UnusualWhalesClient:
    BASE = "https://api.unusualwhales.com"
    TIMEOUT = 20

    def __init__(self):
        key = os.environ.get("UW_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "UW_API_KEY not set. Get your key at "
                "unusualwhales.com/settings/api-dashboard"
            )
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{self.BASE}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=self.TIMEOUT)
        except requests.exceptions.ConnectionError as e:
            raise UnusualWhalesError(f"Connection failed: {e}")
        except requests.exceptions.Timeout:
            raise UnusualWhalesError(f"Timeout on {path}")

        if resp.status_code == 401:
            raise UnusualWhalesError("Invalid UW_API_KEY — check unusualwhales.com/settings/api-dashboard")
        if resp.status_code == 429:
            raise UnusualWhalesError("Rate limited by Unusual Whales — slow down requests")
        if not resp.ok:
            raise UnusualWhalesError(f"HTTP {resp.status_code} on {path}: {resp.text[:200]}")

        return resp.json()

    def ping(self) -> bool:
        """Return True if API key is valid and reachable."""
        try:
            self.market_tide()
            return True
        except UnusualWhalesError:
            return False

    # ── Options Flow ──────────────────────────────────────────────────────

    def flow_alerts(
        self,
        ticker: str = None,
        min_premium: int = 50_000,   # $50K minimum — filter noise
        limit: int = 50,
        is_sweep: bool = None,
        min_dte: int = 0,
        max_dte: int = 60,          # focus on near-term options
    ) -> list[dict]:
        """Unusual options flow alerts. Primary signal source."""
        params = {
            "limit": limit,
            "min_premium": min_premium,
            "min_dte": min_dte,
            "max_dte": max_dte,
        }
        if ticker:
            params["ticker_symbol"] = ticker
        if is_sweep is not None:
            params["is_sweep"] = str(is_sweep).lower()
        data = self._get("/api/option-trades/flow-alerts", params)
        return data if isinstance(data, list) else data.get("data", [])

    def unusual_tickers(self) -> list[dict]:
        """Tickers with unusual options activity right now."""
        data = self._get("/api/option-trades/flow-alerts/tickers")
        return data if isinstance(data, list) else data.get("data", [])

    # ── Dark Pool ─────────────────────────────────────────────────────────

    def darkpool_recent(
        self,
        min_premium: int = 500_000,  # $500K dark pool prints only
        limit: int = 50,
    ) -> list[dict]:
        """Recent large dark pool prints across the market."""
        params = {"limit": limit, "min_premium": min_premium}
        data = self._get("/api/darkpool/recent", params)
        return data if isinstance(data, list) else data.get("data", [])

    def darkpool_ticker(self, ticker: str, limit: int = 20) -> list[dict]:
        """Dark pool activity for a specific symbol."""
        params = {"limit": limit}
        data = self._get(f"/api/darkpool/{ticker}", params)
        return data if isinstance(data, list) else data.get("data", [])

    # ── Market-Wide ───────────────────────────────────────────────────────

    def market_tide(self, interval_5m: bool = True) -> dict:
        """Net premium flow direction across the whole market."""
        params = {"interval_5m": "true" if interval_5m else "false"}
        return self._get("/api/market/market-tide", params)

    def oi_change(self, limit: int = 20) -> list[dict]:
        """Tickers with the largest open interest change today."""
        params = {"limit": limit}
        data = self._get("/api/market/oi-change", params)
        return data if isinstance(data, list) else data.get("data", [])

    def top_net_impact(self, limit: int = 20) -> list[dict]:
        """Tickers with highest net options premium impact today."""
        params = {"limit": limit}
        data = self._get("/api/market/net-flow", params)
        return data if isinstance(data, list) else data.get("data", [])

    def economic_calendar(self) -> list[dict]:
        """Upcoming macro events — fed, CPI, jobs, etc."""
        data = self._get("/api/market/economic-calendar")
        return data if isinstance(data, list) else data.get("data", [])

    # ── Screener ──────────────────────────────────────────────────────────

    def stock_screener(
        self,
        min_volume: int = 500_000,
        min_oi_change_perc: float = 10.0,  # OI growing > 10%
        order: str = "total_oi_change_perc",
        limit: int = 20,
    ) -> list[dict]:
        """UW stock screener — finds tickers with unusual OI/flow activity."""
        params = {
            "min_volume": min_volume,
            "min_total_oi_change_perc": min_oi_change_perc,
            "order": order,
            "order_direction": "desc",
            "limit": limit,
        }
        data = self._get("/api/screener/stocks", params)
        return data if isinstance(data, list) else data.get("data", [])
