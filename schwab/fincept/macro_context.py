"""
Pull macro/geopolitical context from Fincept to inform the SignalAgent. Called
once per pipeline run (not per symbol). Returns "" when Fincept is unavailable.
"""

from __future__ import annotations

from .client import FinceptMCPClient, FinceptMCPError


def get_macro_context(fincept: FinceptMCPClient | None) -> str:
    if fincept is None:
        return ""
    parts = []
    try:
        alerts = fincept.get_threat_alerts(limit=3)
        if alerts:
            parts.append(f"THREAT ALERTS: {alerts}")
    except FinceptMCPError:
        pass
    try:
        geo = fincept.fetch_geopolitics_events(limit=3)
        if geo:
            parts.append(f"GEOPOLITICS: {geo}")
    except FinceptMCPError:
        pass
    return "\n".join(parts)
