"""Shared Anthropic helper for the agents (SDK used directly, no frameworks)."""

from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic
from loguru import logger

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
_MAX_TOKENS = 1024

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set (see .env.example).")
        _client = Anthropic()
    return _client


def ask_claude(system: str, user: str, max_tokens: int = _MAX_TOKENS) -> str:
    """Single-turn completion. Returns the text content (empty string on error)."""
    try:
        resp = _get_client().messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip()
    except Exception as e:  # noqa: BLE001
        logger.error("Claude call failed: {}", e)
        return ""


def extract_json(text: str):
    """Pull the first JSON object/array out of a model response (handles ```json
    fences and leading prose). Returns the parsed value or None."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", candidate, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None
