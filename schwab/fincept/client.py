"""
HTTP client for the FinceptTerminal MCP bridge.

Wire protocol (from TerminalMcpBridge.h):
  POST /tool   body: {"id": str, "tool": str, "args": {}}
               headers: X-MCP-Token, Content-Type: application/json
               response: ToolResult JSON
  GET /tools   headers: X-MCP-Token
               response: [{name, description, inputSchema}]

Connection is close-after-response (no keep-alive); each call opens a new one.
"""

from __future__ import annotations

import uuid

import requests
from loguru import logger

from .config import FinceptConfig


class FinceptMCPError(Exception):
    pass


class FinceptMCPClient:
    def __init__(self, config: FinceptConfig, timeout: int = 15):
        self.config = config
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-MCP-Token": config.token,
                "Content-Type": "application/json",
                "Connection": "close",
            }
        )

    def call_tool(self, tool: str, args: dict) -> dict:
        """Call a Fincept MCP tool; return the parsed JSON result. Raises
        FinceptMCPError on non-2xx or connection failure."""
        payload = {"id": str(uuid.uuid4()), "tool": tool, "args": args}
        try:
            resp = self._session.post(
                f"{self.config.endpoint}/tool", json=payload, timeout=self.timeout
            )
        except requests.exceptions.ConnectionError:
            raise FinceptMCPError(
                f"Cannot connect to FinceptTerminal at {self.config.endpoint}. "
                "Is the app running? Update FINCEPT_MCP_ENDPOINT with the current port."
            )
        except requests.exceptions.Timeout:
            raise FinceptMCPError(f"Tool call '{tool}' timed out after {self.timeout}s")

        if resp.status_code == 401:
            raise FinceptMCPError(
                "Invalid MCP token. Update FINCEPT_MCP_TOKEN — it changes each "
                "time FinceptTerminal restarts."
            )
        if not resp.ok:
            raise FinceptMCPError(
                f"Tool '{tool}' returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError as e:
            raise FinceptMCPError(f"Tool '{tool}' returned non-JSON: {e}")

    def list_tools(self) -> list[dict]:
        """Return the full tool catalog from Fincept."""
        try:
            resp = self._session.get(f"{self.config.endpoint}/tools", timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise FinceptMCPError(f"Cannot connect to FinceptTerminal at {self.config.endpoint}")
        except requests.exceptions.RequestException as e:
            raise FinceptMCPError(f"/tools failed: {e}")

    def ping(self) -> bool:
        """True if the bridge is reachable and the token is valid."""
        try:
            self.list_tools()
            return True
        except FinceptMCPError:
            return False

    # ── convenience wrappers for tools used by ResearchAgent ─────────────────
    def get_quote(self, symbol: str) -> dict:
        return self.call_tool("get_quote", {"symbol": symbol})

    def get_history(self, symbol: str, interval: str = "5m", period: str = "1d") -> dict:
        return self.call_tool("get_history", {"symbol": symbol, "interval": interval, "period": period})

    def get_news(self, symbol: str | None = None, limit: int = 10) -> dict:
        args = {"limit": limit}
        if symbol:
            args["symbol"] = symbol
        return self.call_tool("get_news", args)

    def search_news(self, query: str, limit: int = 5) -> dict:
        return self.call_tool("search_news", {"query": query, "limit": limit})

    def get_threat_alerts(self, limit: int = 5) -> dict:
        return self.call_tool("get_threat_alerts", {"limit": limit})

    def get_equity_technicals(self, symbol: str) -> dict:
        return self.call_tool("get_equity_technicals", {"symbol": symbol})

    def get_equity_sentiment(self, symbol: str) -> dict:
        return self.call_tool("get_equity_sentiment", {"symbol": symbol})

    def fetch_geopolitics_events(self, limit: int = 5) -> dict:
        return self.call_tool("fetch_geopolitics_events", {"limit": limit})

    def datahub_peek(self, topic: str) -> dict:
        return self.call_tool("datahub_peek", {"topic": topic})
