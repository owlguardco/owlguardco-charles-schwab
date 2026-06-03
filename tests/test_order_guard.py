import json

import pytest

from schwab.safety import Mandate, OrderGuard
from schwab.safety.kill_switch import KillSwitch


@pytest.fixture
def mandate():
    return Mandate(symbol_allowlist=["AAPL", "TSLA"], max_position_usd=500, daily_loss_limit_usd=200)


@pytest.fixture
def inactive_kill(tmp_path):
    ks = KillSwitch(state_path=tmp_path / "ks.json")
    ks.deactivate()
    return ks


@pytest.fixture
def active_kill(tmp_path):
    ks = KillSwitch(state_path=tmp_path / "ks.json")
    ks.activate("test halt")
    return ks


def test_happy_path(mandate, inactive_kill):
    g = OrderGuard()
    ok, reason = g.pre_flight("AAPL", 2, 100.0, "BUY", mandate, inactive_kill)
    assert ok is True
    assert reason == "ok"


def test_kill_switch_blocks_everything(mandate, active_kill):
    g = OrderGuard()
    ok, reason = g.pre_flight("AAPL", 1, 10.0, "BUY", mandate, active_kill)
    assert ok is False
    assert "kill switch" in reason


def test_symbol_not_in_allowlist_blocks(mandate, inactive_kill):
    g = OrderGuard()
    ok, reason = g.pre_flight("GME", 1, 10.0, "BUY", mandate, inactive_kill)
    assert ok is False
    assert "allowlist" in reason


def test_size_over_cap_blocks(mandate, inactive_kill):
    g = OrderGuard()
    ok, reason = g.pre_flight("AAPL", 10, 100.0, "BUY", mandate, inactive_kill)  # $1000 > $500
    assert ok is False
    assert "exceeds mandate cap" in reason


def test_bad_side_and_qty_block(mandate, inactive_kill):
    g = OrderGuard()
    assert g.pre_flight("AAPL", 1, 10.0, "HOLD", mandate, inactive_kill)[0] is False
    assert g.pre_flight("AAPL", 0, 10.0, "BUY", mandate, inactive_kill)[0] is False
    assert g.pre_flight("AAPL", 1, 0.0, "BUY", mandate, inactive_kill)[0] is False


def test_duplicate_blocked_within_run(mandate, inactive_kill):
    g = OrderGuard()
    ok1, _ = g.pre_flight("AAPL", 1, 100.0, "BUY", mandate, inactive_kill)
    ok2, reason2 = g.pre_flight("AAPL", 1, 100.0, "BUY", mandate, inactive_kill)
    assert ok1 is True
    assert ok2 is False and "duplicate" in reason2


def test_kill_switch_fails_safe_on_corrupt_state(tmp_path, mandate):
    p = tmp_path / "ks.json"
    p.write_text("{ not valid json")
    ks = KillSwitch(state_path=p)
    assert ks.is_active() is True  # corrupt => treated as ACTIVE (fail safe)
    g = OrderGuard()
    ok, _ = g.pre_flight("AAPL", 1, 100.0, "BUY", mandate, ks)
    assert ok is False
