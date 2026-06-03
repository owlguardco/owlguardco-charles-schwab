"""
TradingPipeline — orchestrates research -> signal -> risk -> execution with the
safety layer wired in. The kill-switch check is ALWAYS the first thing run() does.
"""

from __future__ import annotations

import os

from loguru import logger

from ..agents import ExecutionAgent, ResearchAgent, RiskAgent, SignalAgent
from ..client import AccountsClient, MarketDataClient, OrdersClient
from ..discord import DiscordNotifier
from ..safety import KillSwitch, Mandate, OrderGuard


class TradingPipeline:
    def __init__(self):
        self.notifier = DiscordNotifier()
        self.kill_switch = KillSwitch(notifier=self.notifier)
        self.mandate = Mandate.from_env()
        self.account_hash = os.environ.get("SCHWAB_ACCOUNT_HASH", "")

        self.market_data = MarketDataClient()
        self.accounts = AccountsClient()
        self.orders = OrdersClient()

        self.research_agent = ResearchAgent(self.market_data)
        self.signal_agent = SignalAgent()
        self.risk_agent = RiskAgent(self.market_data)
        self.execution_agent = ExecutionAgent()
        self.order_guard = OrderGuard()

    def run(self, symbols: list[str]) -> dict:
        # 1. Kill switch FIRST — always.
        if self.kill_switch.is_active():
            msg = f"kill switch active: {self.kill_switch.reason()}"
            logger.error("ABORT — {}", msg)
            self.notifier.send("⛔ Run aborted", msg, color=0xFF0000)
            return {"status": "aborted", "reason": msg}

        if not self.account_hash:
            msg = "SCHWAB_ACCOUNT_HASH not set — run scripts/auth_setup.py / account_status.py"
            logger.error(msg)
            return {"status": "error", "reason": msg}

        symbols = [s.upper() for s in symbols if s]
        # Mandate allowlist is the outer boundary — never even research off-list names.
        symbols = [s for s in symbols if self.mandate.allows_symbol(s)]
        if not symbols:
            return {"status": "no_symbols", "reason": "no allowlisted symbols to trade"}

        self.order_guard.reset()

        # 2. Account value (for sizing).
        account_value = self.accounts.get_account_value(self.account_hash)
        logger.info("account value: ${:,.2f}", account_value)

        # 3-4. Research -> signals.
        research = self.research_agent.run(symbols)
        signals = self.signal_agent.run(research)
        if not signals:
            logger.info("no signals")
            self.notifier.send("📊 Run complete", "No actionable signals.", color=0x808080)
            return {"status": "no_signals"}

        # 6-7. Risk sizing.
        sized = self.risk_agent.run(signals, account_value, self.mandate)
        if not sized:
            logger.info("no sized signals")
            self.notifier.send("📊 Run complete", "Signals found but none sized.", color=0x808080)
            return {"status": "no_sized_signals", "signals": signals}

        # 8. Execution (every order pre-flighted; errors trip the kill switch).
        results = self.execution_agent.run(
            sized, self.account_hash, self.orders, self.order_guard,
            self.kill_switch, self.mandate, self.notifier,
        )

        # 9. Summary.
        submitted = [r for r in results if r.get("result") == "submitted"]
        blocked = [r for r in results if r.get("result") == "blocked"]
        errored = [r for r in results if r.get("result") == "error"]
        summary = (
            f"submitted {len(submitted)} · blocked {len(blocked)} · errors {len(errored)} "
            f"(of {len(sized)} sized)"
        )
        self.notifier.send("📊 Trading run complete", summary,
                           color=0xFF0000 if errored else 0x00FF00)
        logger.info("run complete: {}", summary)
        return {
            "status": "complete", "summary": summary,
            "submitted": submitted, "blocked": blocked, "errors": errored,
        }
