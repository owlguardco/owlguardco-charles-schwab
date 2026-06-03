"""
Mandate — the hard trading constraints, loaded from env. Symbol allowlist, max
per-position dollar size, daily loss limit. The mandate is the first gate the
order guard checks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Mandate:
    symbol_allowlist: list[str] = field(default_factory=list)
    max_position_usd: float = 0.0
    daily_loss_limit_usd: float = 0.0

    @classmethod
    def from_env(cls) -> "Mandate":
        raw = os.environ.get("MANDATE_SYMBOL_ALLOWLIST", "")
        allowlist = [s.strip().upper() for s in raw.split(",") if s.strip()]
        try:
            max_pos = float(os.environ.get("MANDATE_MAX_POSITION_USD", "0") or 0)
        except ValueError:
            max_pos = 0.0
        try:
            daily_loss = float(os.environ.get("MANDATE_DAILY_LOSS_LIMIT_USD", "0") or 0)
        except ValueError:
            daily_loss = 0.0
        return cls(
            symbol_allowlist=allowlist,
            max_position_usd=max_pos,
            daily_loss_limit_usd=daily_loss,
        )

    def allows_symbol(self, symbol: str) -> bool:
        return bool(symbol) and symbol.upper() in self.symbol_allowlist

    def allows_size(self, qty: int, price: float) -> bool:
        """A position is allowed only if its notional is within the cap AND the
        cap is configured (> 0). A zero/blank cap fails closed."""
        if self.max_position_usd <= 0 or qty < 1 or price <= 0:
            return False
        return (qty * price) <= self.max_position_usd
