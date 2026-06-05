"""Tests for yfinance options chain module."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd


def test_get_chain_snapshot_returns_error_on_no_options():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.options = []
        from schwab.options.chain import get_chain_snapshot
        result = get_chain_snapshot("FAKE")
    assert result["error"] is not None
    assert result["symbol"] == "FAKE"


def test_get_chain_snapshot_handles_import_error():
    import sys
    with patch.dict(sys.modules, {"yfinance": None}):
        # Force reimport
        if "schwab.options.chain" in sys.modules:
            del sys.modules["schwab.options.chain"]
        from schwab.options.chain import get_chain_snapshot
        result = get_chain_snapshot("AAPL")
    # Should return error gracefully
    assert "symbol" in result


def test_get_market_flow_free_caps_symbols():
    with patch("schwab.options.chain.get_chain_snapshot") as mock_snap:
        mock_snap.return_value = {"symbol": "X", "unusual_volume": [], "error": None}
        from schwab.options.chain import get_market_flow_free
        result = get_market_flow_free(["A","B","C","D","E","F","G","H","I","J","K","L"])
    # Should cap at 10
    assert mock_snap.call_count <= 10


def test_get_options_snapshot_skips_when_uw_configured():
    import os
    from dashboard.state import get_options_snapshot
    with patch.dict(os.environ, {"UW_API_KEY": "test-key"}):
        result = get_options_snapshot(["AAPL"])
    assert result == {}
