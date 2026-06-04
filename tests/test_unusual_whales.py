"""Tests for UnusualWhalesClient — mocked HTTP."""
import pytest
from unittest.mock import patch, MagicMock
import os


def test_client_raises_without_key():
    from schwab.unusual_whales.client import UnusualWhalesClient
    with patch.dict(os.environ, {}, clear=True):
        # Remove UW_API_KEY if present
        env = {k: v for k, v in os.environ.items() if k != "UW_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError, match="UW_API_KEY"):
                UnusualWhalesClient()


def test_flow_alerts_passes_params():
    with patch.dict(os.environ, {"UW_API_KEY": "test-key"}):
        from schwab.unusual_whales.client import UnusualWhalesClient
        client = UnusualWhalesClient()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            result = client.flow_alerts(ticker="AAPL", min_premium=100_000)
        call_params = mock_get.call_args[1]["params"]
        assert call_params["ticker_symbol"] == "AAPL"
        assert call_params["min_premium"] == 100_000
        assert result == []


def test_get_market_flow_summary_empty_when_no_client():
    from schwab.unusual_whales.flow_context import get_market_flow_summary
    assert get_market_flow_summary(None) == ""
