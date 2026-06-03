"""
DiscordNotifier — posts trade/kill-switch/run alerts as Discord embeds. If
DISCORD_WEBHOOK_URL is unset it logs to console instead. NEVER raises — a
notification failure must never break (or worse, half-break) a trading run.
"""

from __future__ import annotations

import os

import requests
from loguru import logger


class DiscordNotifier:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")

    def send(self, title: str, message: str, color: int = 0x00FF00) -> None:
        if not self.webhook_url:
            logger.info("[discord:console] {} — {}", title, message)
            return
        payload = {"embeds": [{"title": title, "description": message, "color": color}]}
        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"User-Agent": "owlguardco-schwab/0.1"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Discord post failed: {} {}", resp.status_code, resp.text[:120])
        except Exception as e:  # noqa: BLE001 — never propagate
            logger.warning("Discord notify error (non-fatal): {}", e)
