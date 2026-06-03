import os

from schwab.safety import Mandate


def test_from_env_parses_allowlist_and_limits(monkeypatch):
    monkeypatch.setenv("MANDATE_SYMBOL_ALLOWLIST", "aapl, tsla ,NVDA")
    monkeypatch.setenv("MANDATE_MAX_POSITION_USD", "500")
    monkeypatch.setenv("MANDATE_DAILY_LOSS_LIMIT_USD", "200")
    m = Mandate.from_env()
    assert m.symbol_allowlist == ["AAPL", "TSLA", "NVDA"]
    assert m.max_position_usd == 500.0
    assert m.daily_loss_limit_usd == 200.0


def test_allows_symbol_is_case_insensitive():
    m = Mandate(symbol_allowlist=["AAPL", "SPY"], max_position_usd=500, daily_loss_limit_usd=200)
    assert m.allows_symbol("aapl") is True
    assert m.allows_symbol("AAPL") is True
    assert m.allows_symbol("GME") is False
    assert m.allows_symbol("") is False


def test_allows_size_respects_cap():
    m = Mandate(symbol_allowlist=["AAPL"], max_position_usd=500, daily_loss_limit_usd=200)
    assert m.allows_size(2, 100.0) is True       # $200 <= $500
    assert m.allows_size(5, 100.0) is True        # $500 == cap
    assert m.allows_size(6, 100.0) is False       # $600 > $500
    assert m.allows_size(0, 100.0) is False       # qty < 1
    assert m.allows_size(1, 0.0) is False         # bad price


def test_allows_size_fails_closed_with_zero_cap():
    m = Mandate(symbol_allowlist=["AAPL"], max_position_usd=0, daily_loss_limit_usd=200)
    assert m.allows_size(1, 1.0) is False
