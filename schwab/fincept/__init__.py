"""FinceptTerminal MCP bridge integration (optional research data source)."""

from .config import FinceptConfig
from .client import FinceptMCPClient, FinceptMCPError

__all__ = ["FinceptConfig", "FinceptMCPClient", "FinceptMCPError"]
