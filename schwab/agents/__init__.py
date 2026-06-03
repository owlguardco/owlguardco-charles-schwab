"""Agent pipeline: research -> signal -> risk -> execution. Uses the anthropic
SDK directly (no LangChain, no swarms)."""

import os

from .research import ResearchAgent
from .signal import SignalAgent
from .risk import RiskAgent
from .execution import ExecutionAgent

# Default model is overridable. The bootstrap spec named claude-sonnet-4-20250514
# (an older snapshot); default here is the current Sonnet. Pin via ANTHROPIC_MODEL.
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 1024

__all__ = [
    "ResearchAgent",
    "SignalAgent",
    "RiskAgent",
    "ExecutionAgent",
    "DEFAULT_MODEL",
    "MAX_TOKENS",
]
