"""
Live state reader for the dashboard.
Reads from: kill_switch_state.json, trade_log.csv, .env (mandate),
and optionally live Schwab/UW/Fincept clients.

All methods return plain dicts/lists — JSON-serializable, no exceptions raised.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "schwab" / "data"
KILL_SWITCH_PATH = DATA_DIR / "kill_switch_state.json"
TRADE_LOG_PATH = DATA_DIR / "trade_log.csv"


# ── Kill switch ────────────────────────────────────────────────────────────

def get_kill_switch() -> dict:
    try:
        state = json.loads(KILL_SWITCH_PATH.read_text())
        return {
            "active": bool(state.get("active")),
            "reason": state.get("reason", ""),
            "updated_at": state.get("updated_at", ""),
        }
    except FileNotFoundError:
        return {"active": False, "reason": "", "updated_at": ""}
    except Exception as e:
        return {"active": True, "reason": f"unreadable state: {e}", "updated_at": ""}


def set_kill_switch(active: bool, reason: str = "") -> dict:
    """Write kill switch state. Returns new state dict."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": active,
        "reason": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = KILL_SWITCH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(KILL_SWITCH_PATH)
    return payload


# ── Trade log ──────────────────────────────────────────────────────────────

def get_trade_log(limit: int = 50) -> list[dict]:
    if not TRADE_LOG_PATH.exists():
        return []
    try:
        with TRADE_LOG_PATH.open(newline="") as f:
            rows = list(csv.DictReader(f))
        return list(reversed(rows))[:limit]
    except Exception:
        return []


def get_pnl_today() -> dict:
    """
    Estimate today's P&L from trade log.
    Submitted orders with a price are counted as realized.
    Returns {total_pnl, trade_count, win_count}.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    trades = [
        t for t in get_trade_log(200)
        if t.get("result") == "submitted"
        and t.get("timestamp", "")[:10] == today
    ]
    # We don't have exit prices in the log (market orders, intraday)
    # so P&L is approximated as 0 until exit prices are tracked.
    return {
        "total_pnl": 0.0,
        "trade_count": len(trades),
        "win_count": 0,
    }


# ── Mandate ────────────────────────────────────────────────────────────────

def get_mandate() -> dict:
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
    return {
        "symbol_allowlist": allowlist,
        "max_position_usd": max_pos,
        "daily_loss_limit_usd": daily_loss,
    }


# ── Module connectivity status ──────────────────────────────────────────────

def get_module_status() -> dict:
    """
    Check which integrations are configured (not live-ping — fast check only).
    Returns dict of {module: status} where status is 'ready'|'missing'|'configured'.
    """
    schwab_authed = bool(
        os.environ.get("SCHWAB_ACCESS_TOKEN")
        and os.environ.get("SCHWAB_ACCOUNT_HASH")
    )
    fincept_configured = bool(
        os.environ.get("FINCEPT_MCP_ENDPOINT")
        and os.environ.get("FINCEPT_MCP_TOKEN")
    )
    uw_configured = bool(os.environ.get("UW_API_KEY"))
    anthropic_configured = bool(os.environ.get("ANTHROPIC_API_KEY"))

    return {
        "schwab": "ready" if schwab_authed else "missing",
        "fincept": "ready" if fincept_configured else "missing",
        "unusual_whales": "ready" if uw_configured else "missing",
        "anthropic": "ready" if anthropic_configured else "missing",
        "screener": "ready",   # no key needed
        "backtest": "ready",   # no key needed
    }


# ── Live Schwab account (optional — only if authed) ─────────────────────────

def get_account_summary() -> dict:
    """
    Try to fetch live account value + positions from Schwab.
    Returns empty dict on any failure — dashboard degrades gracefully.
    """
    account_hash = os.environ.get("SCHWAB_ACCOUNT_HASH", "")
    if not account_hash or not os.environ.get("SCHWAB_ACCESS_TOKEN"):
        return {}
    try:
        from schwab.auth.oauth import SchwabAuth
        from schwab.client.accounts import AccountsClient
        auth = SchwabAuth()
        client = AccountsClient(auth)
        value = client.get_account_value(account_hash)
        positions = client.get_positions(account_hash)
        return {
            "account_value": value,
            "positions": positions,
        }
    except Exception as e:
        return {"error": str(e)}


# ── Unusual Whales snapshot (optional) ──────────────────────────────────────

def get_uw_snapshot() -> dict:
    """
    Fetch market tide + top OI change from UW.
    Returns empty dict if UW_API_KEY not set or call fails.
    """
    if not os.environ.get("UW_API_KEY"):
        return {}
    try:
        from schwab.unusual_whales.client import UnusualWhalesClient, UnusualWhalesError
        client = UnusualWhalesClient()
        tide = client.market_tide()
        oi = client.oi_change(limit=10)
        flow = client.flow_alerts(min_premium=100_000, limit=20)
        return {"market_tide": tide, "oi_change": oi, "flow_alerts": flow}
    except Exception as e:
        return {"error": str(e)}


# ── Full dashboard snapshot ──────────────────────────────────────────────────

def get_full_snapshot() -> dict:
    """Single call that assembles everything the dashboard needs."""
    return {
        "kill_switch": get_kill_switch(),
        "mandate": get_mandate(),
        "module_status": get_module_status(),
        "trade_log": get_trade_log(50),
        "pnl_today": get_pnl_today(),
        "account": get_account_summary(),
        "uw": get_uw_snapshot(),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
