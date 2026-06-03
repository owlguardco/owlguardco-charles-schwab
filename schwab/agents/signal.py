"""SignalAgent — turns research summaries into concrete trade signals."""

from __future__ import annotations

from loguru import logger

from ._llm import ask_claude, extract_json

SYSTEM = (
    "You are a disciplined intraday signal generator for a single retail trader. "
    "Given research summaries for several stocks, output a JSON array of signals, "
    "one per symbol. Each item: "
    '{"symbol": str, "direction": "LONG"|"SHORT"|"PASS", "entry_note": str, '
    '"confidence": int 0-10}. '
    "Be conservative: use PASS when the setup is weak or unclear. confidence is "
    "your honest read of setup quality, not a promise. Output ONLY the JSON array."
)

MIN_CONFIDENCE = 6


class SignalAgent:
    def run(self, research: dict, macro_context: str = "") -> list[dict]:
        if not research:
            return []
        body = "\n\n".join(f"### {sym}\n{summary}" for sym, summary in research.items())
        prompt = f"Research summaries:\n\n{body}"
        if macro_context:
            prompt += (
                "\n\nMACRO/GEOPOLITICAL CONTEXT (factor this into signal "
                f"confidence):\n{macro_context}"
            )
        raw = ask_claude(SYSTEM, prompt)
        parsed = extract_json(raw)
        if not isinstance(parsed, list):
            logger.warning("signal agent returned non-list; no signals")
            return []
        signals = []
        for s in parsed:
            if not isinstance(s, dict):
                continue
            direction = str(s.get("direction", "PASS")).upper()
            try:
                conf = int(s.get("confidence", 0))
            except (TypeError, ValueError):
                conf = 0
            if direction in ("LONG", "SHORT") and conf >= MIN_CONFIDENCE and s.get("symbol"):
                signals.append({
                    "symbol": str(s["symbol"]).upper(),
                    "direction": direction,
                    "entry_note": str(s.get("entry_note", "")),
                    "confidence": conf,
                })
        logger.info("signals: {} actionable (>= conf {})", len(signals), MIN_CONFIDENCE)
        return signals
