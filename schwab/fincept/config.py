"""
Fincept Terminal MCP bridge discovery.

The port and token change every time FinceptTerminal launches. Store them in
.env as FINCEPT_MCP_ENDPOINT and FINCEPT_MCP_TOKEN. Update after each restart:
  python scripts/fincept_discover.py
Or set them manually from Fincept's Settings -> Developer -> MCP Bridge.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class FinceptConfig:
    # Defaults are "" so FinceptConfig() constructs even when nothing is set yet
    # (callers use is_configured() to decide, then from_env() to validate).
    endpoint: str = ""    # e.g. "http://127.0.0.1:54321"
    token: str = ""       # per-process UUID from Fincept

    @classmethod
    def from_env(cls) -> "FinceptConfig":
        endpoint = os.environ.get("FINCEPT_MCP_ENDPOINT", "")
        token = os.environ.get("FINCEPT_MCP_TOKEN", "")
        if not endpoint or not token:
            raise EnvironmentError(
                "FINCEPT_MCP_ENDPOINT and FINCEPT_MCP_TOKEN must be set. "
                "Run: python scripts/fincept_discover.py"
            )
        return cls(endpoint=endpoint, token=token)

    def is_configured(self) -> bool:
        """True if both env values are present. Reads the environment directly,
        so it works on a bare FinceptConfig() instance."""
        return bool(
            os.environ.get("FINCEPT_MCP_ENDPOINT", "")
            and os.environ.get("FINCEPT_MCP_TOKEN", "")
        )
