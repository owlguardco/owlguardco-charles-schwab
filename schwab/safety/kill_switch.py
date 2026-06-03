"""
KillSwitch — a file-backed global halt. Checked before every order and at the
very start of every pipeline run. When active, NO orders are placed. It must be
deactivated deliberately (manual or scripted); it never auto-clears.

State file: schwab/data/kill_switch_state.json -> {"active": bool, "reason": str,
"updated_at": iso}. A missing/unreadable file is treated as INACTIVE (the system
is usable out of the box) — but any write failure on activate() is logged loudly
because a kill switch that can't persist is a safety hole.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "kill_switch_state.json"


class KillSwitch:
    def __init__(self, state_path: Path | str = STATE_PATH, notifier=None):
        self.state_path = Path(state_path)
        self.notifier = notifier  # optional DiscordNotifier; alerts on activate

    def _read(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return {"active": False, "reason": ""}
        except Exception as e:  # corrupt file — fail SAFE (treat as active)
            logger.error("kill_switch state unreadable ({}); failing safe = ACTIVE", e)
            return {"active": True, "reason": f"unreadable state file: {e}"}

    def _write(self, active: bool, reason: str) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active": active,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(self.state_path)

    def is_active(self) -> bool:
        return bool(self._read().get("active"))

    def reason(self) -> str:
        return str(self._read().get("reason", ""))

    def activate(self, reason: str) -> None:
        try:
            self._write(True, reason)
            logger.error("KILL SWITCH ACTIVATED: {}", reason)
        except Exception as e:
            logger.critical("FAILED to persist kill switch ({}) — halt anyway", e)
        if self.notifier:
            try:
                self.notifier.send(
                    "🛑 Kill switch ACTIVATED",
                    f"Trading halted. Reason: {reason}",
                    color=0xFF0000,
                )
            except Exception:
                pass

    def deactivate(self) -> None:
        self._write(False, "")
        logger.info("Kill switch deactivated")
