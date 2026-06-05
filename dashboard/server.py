"""
Flask dashboard server.

Routes:
  GET  /                    — serve dashboard HTML
  GET  /api/snapshot        — full JSON snapshot (polled every 10s by frontend)
  GET  /api/kill-switch     — current kill switch state
  POST /api/kill-switch     — {active: bool, reason: str} — toggle
  GET  /api/trade-log       — recent trades
  GET  /api/uw/flow         — live UW flow alerts (on-demand)
  POST /api/pipeline/run    — {symbols: [...]} — run pipeline in background thread
  GET  /api/pipeline/status — last pipeline run result
  GET  /events              — SSE stream for live push updates

Run with:
  python dashboard/server.py
  # or: .venv/bin/python dashboard/server.py
"""
from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS
from loguru import logger

from dashboard.state import (
    get_full_snapshot,
    get_kill_switch,
    get_trade_log,
    get_uw_snapshot,
    set_kill_switch,
)

app = Flask(__name__)
CORS(app)

HTML_PATH = Path(__file__).parent / "static" / "index.html"

# ── SSE event bus ──────────────────────────────────────────────────────────
_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _broadcast(event_type: str, data: dict) -> None:
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


# ── Background poller: pushes snapshot every 10s ───────────────────────────
def _poll_loop():
    while True:
        try:
            snap = get_full_snapshot()
            _broadcast("snapshot", snap)
        except Exception as e:
            logger.warning(f"Poll loop error: {e}")
        time.sleep(10)


# Init DB schema on startup (no-op if DATABASE_URL not set)
try:
    from dashboard.db import init_schema
    init_schema()
except Exception as _e:
    logger.warning(f"DB init skipped: {_e}")

threading.Thread(target=_poll_loop, daemon=True).start()

# ── Pipeline run state ──────────────────────────────────────────────────────
_pipeline_lock = threading.Lock()
_pipeline_state = {"status": "idle", "last_run": None, "result": None}


def _run_pipeline_bg(symbols: list[str]) -> None:
    global _pipeline_state
    with _pipeline_lock:
        _pipeline_state = {"status": "running", "last_run": datetime.now(timezone.utc).isoformat(), "result": None}
    _broadcast("pipeline_status", _pipeline_state)
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from schwab.pipeline.runner import TradingPipeline
        pipeline = TradingPipeline()
        result = pipeline.run(symbols)
        with _pipeline_lock:
            _pipeline_state = {"status": "complete", "last_run": _pipeline_state["last_run"], "result": result}
    except Exception as e:
        with _pipeline_lock:
            _pipeline_state = {"status": "error", "last_run": _pipeline_state["last_run"], "result": {"error": str(e)}}
    _broadcast("pipeline_status", _pipeline_state)
    # After pipeline run, push a fresh snapshot so dashboard updates immediately
    _broadcast("snapshot", get_full_snapshot())


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file(HTML_PATH)


@app.route("/api/snapshot")
def api_snapshot():
    return jsonify(get_full_snapshot())


@app.route("/api/kill-switch", methods=["GET"])
def api_ks_get():
    return jsonify(get_kill_switch())


@app.route("/api/kill-switch", methods=["POST"])
def api_ks_set():
    body = request.get_json(force=True, silent=True) or {}
    active = bool(body.get("active", False))
    reason = str(body.get("reason", "dashboard toggle"))
    state = set_kill_switch(active, reason)
    logger.info(f"Kill switch set to active={active} via dashboard")
    _broadcast("kill_switch", state)
    return jsonify(state)


@app.route("/api/trade-log")
def api_trade_log():
    limit = int(request.args.get("limit", 50))
    return jsonify(get_trade_log(limit))


@app.route("/api/uw/flow")
def api_uw_flow():
    return jsonify(get_uw_snapshot())


@app.route("/api/options/free")
def api_options_free():
    from dashboard.state import get_options_snapshot
    symbols = request.args.get("symbols", "").upper().split(",")
    symbols = [s.strip() for s in symbols if s.strip()]
    return jsonify(get_options_snapshot(symbols or None))


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    if _pipeline_state.get("status") == "running":
        return jsonify({"error": "pipeline already running"}), 409
    body = request.get_json(force=True, silent=True) or {}
    symbols = body.get("symbols", [])
    if not symbols:
        return jsonify({"error": "symbols required"}), 400
    thread = threading.Thread(target=_run_pipeline_bg, args=(symbols,), daemon=True)
    thread.start()
    return jsonify({"status": "started", "symbols": symbols})


@app.route("/api/pipeline/status")
def api_pipeline_status():
    return jsonify(_pipeline_state)


@app.route("/events")
def sse_stream():
    q: queue.Queue = queue.Queue(maxsize=20)
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        # Send immediate snapshot on connect
        try:
            snap = get_full_snapshot()
            yield f"event: snapshot\ndata: {json.dumps(snap)}\n\n"
        except Exception:
            pass
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": heartbeat\n\n"  # keep connection alive
        finally:
            with _sse_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Dashboard starting at http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
