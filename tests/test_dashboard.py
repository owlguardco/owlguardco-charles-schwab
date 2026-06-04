"""Tests for dashboard state reader — no network calls."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_kill_switch_missing_file_returns_inactive():
    from dashboard.state import get_kill_switch
    with patch("dashboard.state.KILL_SWITCH_PATH", Path("/nonexistent/path.json")):
        result = get_kill_switch()
    assert result["active"] is False


def test_kill_switch_corrupt_file_returns_active():
    import tempfile, os
    from dashboard.state import get_kill_switch
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("not json {{{{")
        tmp = Path(f.name)
    try:
        with patch("dashboard.state.KILL_SWITCH_PATH", tmp):
            result = get_kill_switch()
        assert result["active"] is True
    finally:
        os.unlink(tmp)


def test_set_kill_switch_writes_correctly():
    import tempfile, os
    from dashboard.state import set_kill_switch
    with tempfile.TemporaryDirectory() as tmpdir:
        ks_path = Path(tmpdir) / "ks.json"
        with patch("dashboard.state.KILL_SWITCH_PATH", ks_path), \
             patch("dashboard.state.DATA_DIR", Path(tmpdir)):
            result = set_kill_switch(True, "test reason")
    assert result["active"] is True
    assert result["reason"] == "test reason"


def test_trade_log_empty_when_no_file():
    from dashboard.state import get_trade_log
    with patch("dashboard.state.TRADE_LOG_PATH", Path("/nonexistent/trade_log.csv")):
        result = get_trade_log()
    assert result == []


def test_get_mandate_reads_env():
    from dashboard.state import get_mandate
    with patch.dict("os.environ", {
        "MANDATE_SYMBOL_ALLOWLIST": "AAPL,TSLA,NVDA",
        "MANDATE_MAX_POSITION_USD": "500",
        "MANDATE_DAILY_LOSS_LIMIT_USD": "200",
    }):
        m = get_mandate()
    assert "AAPL" in m["symbol_allowlist"]
    assert m["max_position_usd"] == 500.0
    assert m["daily_loss_limit_usd"] == 200.0


def test_module_status_missing_when_no_keys():
    from dashboard.state import get_module_status
    with patch.dict("os.environ", {}, clear=True):
        status = get_module_status()
    assert status["schwab"] == "missing"
    assert status["screener"] == "ready"
    assert status["backtest"] == "ready"


def test_flask_snapshot_route():
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test")
    from dashboard.server import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/snapshot")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kill_switch" in data
    assert "mandate" in data
    assert "module_status" in data


def test_flask_kill_switch_toggle():
    from dashboard.server import app
    app.config["TESTING"] = True
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        ks_path = Path(tmpdir) / "ks.json"
        with patch("dashboard.state.KILL_SWITCH_PATH", ks_path), \
             patch("dashboard.state.DATA_DIR", Path(tmpdir)):
            with app.test_client() as client:
                resp = client.post("/api/kill-switch",
                    json={"active": True, "reason": "test"},
                    content_type="application/json")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["active"] is True
