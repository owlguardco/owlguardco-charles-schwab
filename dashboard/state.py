"""
Live state reader for the dashboard.

Storage priority:
  1. Postgres (DATABASE_URL set) — used on Railway
  2. Local files — used in local dev without DB

All methods return plain dicts/lists — JSON-serializable, no exceptions raised.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "schwab" / "data"
KILL_SWITCH_PATH = DATA_DIR / "kill_switch_state.json"
TRADE_LOG_PATH = DATA_DIR / "trade_log.csv"


# ── Kill switch ────────────────────────────────────────────────────────────

def get_kill_switch() -> dict:
    from dashboard.db import db_get_kill_switch
    db = db_get_kill_switch()
    if db is not None:
        return db
    # Local file fallback
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
    from dashboard.db import db_set_kill_switch, is_configured
    if is_configured():
        result = db_set_kill_switch(active, reason)
        if result:
            return result
    # Local file fallback
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
    from dashboard.db import db_get_trades
    db = db_get_trades(limit)
    if db is not None:
        return db
    # Local file fallback
    if not TRADE_LOG_PATH.exists():
        return []
    try:
        with TRADE_LOG_PATH.open(newline="") as f:
            rows = list(csv.DictReader(f))
        return list(reversed(rows))[:limit]
    except Exception:
        return []


def get_pnl_today() -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    trades = [
        t for t in get_trade_log(200)
        if t.get("result") == "submitted"
        and str(t.get("timestamp", ""))[:10] == today
    ]
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
    from dashboard.db import is_configured as db_configured
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
        "screener": "ready",
        "backtest": "ready",
        "database": "ready" if db_configured() else "missing",
    }


# ── Live Schwab account ─────────────────────────────────────────────────────

def get_account_summary() -> dict:
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
        return {"account_value": value, "positions": positions}
    except Exception as e:
        return {"error": str(e)}


# ── Unusual Whales snapshot ─────────────────────────────────────────────────

def get_uw_snapshot() -> dict:
    if not os.environ.get("UW_API_KEY"):
        return {}
    try:
        from schwab.unusual_whales.client import UnusualWhalesClient
        client = UnusualWhalesClient()
        tide = client.market_tide()
        oi = client.oi_change(limit=10)
        flow = client.flow_alerts(min_premium=100_000, limit=20)
        return {"market_tide": tide, "oi_change": oi, "flow_alerts": flow}
    except Exception as e:
        return {"error": str(e)}


# ── Fincept snapshot ─────────────────────────────────────────────────────────

def get_fincept_snapshot() -> dict:
    """
    Fetch live data from Fincept MCP bridge.
    Returns empty dict if not configured or unreachable.
    """
    if not os.environ.get("FINCEPT_MCP_ENDPOINT"):
        return {}
    try:
        from schwab.fincept.config import FinceptConfig
        from schwab.fincept.client import FinceptMCPClient, FinceptMCPError
        from schwab.fincept.macro_context import get_macro_context
        cfg = FinceptConfig.from_env()
        client = FinceptMCPClient(cfg)
        if not client.ping():
            return {"error": "bridge unreachable"}
        result = {}
        try:
            result["market_tide"] = client.datahub_peek("market:tide")
        except FinceptMCPError:
            pass
        try:
            result["threat_alerts"] = client.get_threat_alerts(limit=3)
        except FinceptMCPError:
            pass
        try:
            result["geopolitics"] = client.fetch_geopolitics_events(limit=3)
        except FinceptMCPError:
            pass
        result["connected"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


# ── Full snapshot ──────────────────────────────────────────────────────────

def get_full_snapshot() -> dict:
    return {
        "kill_switch": get_kill_switch(),
        "mandate": get_mandate(),
        "module_status": get_module_status(),
        "trade_log": get_trade_log(50),
        "pnl_today": get_pnl_today(),
        "account": get_account_summary(),
        "uw": get_uw_snapshot(),
        "fincept": get_fincept_snapshot(),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
