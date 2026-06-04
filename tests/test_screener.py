"""Tests for MomentumScanner — no network calls."""
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from schwab.screener.scanner import MomentumScanner


def test_rank_sorts_by_change():
    scanner = MomentumScanner()
    df = pd.DataFrame({
        "Ticker": ["A", "B", "C"],
        "Change": ["1.5%", "3.2%", "0.8%"],
        "Volume": ["1000000", "500000", "2000000"],
    })
    ranked = scanner._rank(df)
    assert ranked.iloc[0]["Ticker"] == "B"


def test_scan_returns_empty_on_failure():
    scanner = MomentumScanner()
    with patch("schwab.screener.scanner.Overview") as mock_ov:
        mock_ov.return_value.screener_view.side_effect = Exception("network error")
        result = scanner.scan()
    assert result == []


def test_scan_respects_max_symbols():
    scanner = MomentumScanner(max_symbols=3)
    mock_df = pd.DataFrame({
        "Ticker": [f"SYM{i}" for i in range(10)],
        "Change": [f"{i}.0%" for i in range(10, 0, -1)],
        "Volume": ["1000000"] * 10,
    })
    with patch("schwab.screener.scanner.Overview") as mock_ov:
        mock_ov.return_value.screener_view.return_value = mock_df
        result = scanner.scan()
    assert len(result) <= 3
