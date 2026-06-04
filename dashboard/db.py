"""
Postgres persistence layer for kill switch and trade log.

Uses DATABASE_URL env var (set automatically by Railway Postgres plugin).
Falls back to local file storage when DATABASE_URL is not set — local dev
continues to work exactly as before.

Schema (created on first connect):
  kill_switch(id SERIAL PK, active BOOL, reason TEXT, updated_at TIMESTAMPTZ)
  trades(id SERIAL PK, timestamp TIMESTAMPTZ, symbol TEXT, side TEXT,
         qty INT, price NUMERIC, estimated_cost NUMERIC, confidence TEXT,
         result TEXT, order_id TEXT, detail TEXT)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone

from loguru import logger

_pool = None


def _get_url() -> str | None:
    return os.environ.get("DATABASE_URL", "")


def is_configured() -> bool:
    return bool(_get_url())


def _connect():
    import psycopg2
    import psycopg2.extras
    url = _get_url()
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


@contextmanager
def get_conn():
    """Context manager — yields a connection, commits on exit, rolls back on error."""
    conn = None
    try:
        conn = _connect()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def init_schema() -> None:
    """Create tables if they don't exist. Called once at server startup."""
    if not is_configured():
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS kill_switch (
                        id SERIAL PRIMARY KEY,
                        active BOOLEAN NOT NULL DEFAULT FALSE,
                        reason TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    INSERT INTO kill_switch (active, reason, updated_at)
                    SELECT FALSE, '', NOW()
                    WHERE NOT EXISTS (SELECT 1 FROM kill_switch)
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ,
                        symbol TEXT,
                        side TEXT,
                        qty INTEGER,
                        price NUMERIC(12,4),
                        estimated_cost NUMERIC(12,4),
                        confidence TEXT,
                        result TEXT,
                        order_id TEXT,
                        detail TEXT
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS trades_timestamp_idx ON trades(timestamp DESC)
                """)
        logger.info("DB schema initialized")
    except Exception as e:
        logger.error(f"DB schema init failed: {e}")


# ── Kill switch ────────────────────────────────────────────────────────────

def db_get_kill_switch() -> dict | None:
    """Returns kill switch row as dict, or None if DB not configured/error."""
    if not is_configured():
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT active, reason, updated_at FROM kill_switch ORDER BY id DESC LIMIT 1"
                )
                row = cur.fetchone()
                if not row:
                    return {"active": False, "reason": "", "updated_at": ""}
                return {
                    "active": bool(row[0]),
                    "reason": row[1] or "",
                    "updated_at": row[2].isoformat() if row[2] else "",
                }
    except Exception as e:
        logger.error(f"db_get_kill_switch error: {e}")
        return None


def db_set_kill_switch(active: bool, reason: str) -> dict | None:
    """Upsert kill switch row. Returns new state or None on error."""
    if not is_configured():
        return None
    now = datetime.now(timezone.utc)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE kill_switch SET active=%s, reason=%s, updated_at=%s
                    WHERE id=(SELECT id FROM kill_switch ORDER BY id DESC LIMIT 1)
                    """,
                    (active, reason, now),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "INSERT INTO kill_switch (active, reason, updated_at) VALUES (%s,%s,%s)",
                        (active, reason, now),
                    )
        return {"active": active, "reason": reason, "updated_at": now.isoformat()}
    except Exception as e:
        logger.error(f"db_set_kill_switch error: {e}")
        return None


# ── Trade log ──────────────────────────────────────────────────────────────

def db_get_trades(limit: int = 50) -> list[dict] | None:
    """Returns recent trades as list of dicts, or None on error/unconfigured."""
    if not is_configured():
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT timestamp, symbol, side, qty, price, estimated_cost,
                           confidence, result, order_id, detail
                    FROM trades ORDER BY timestamp DESC LIMIT %s
                    """,
                    (limit,),
                )
                cols = ["timestamp","symbol","side","qty","price","estimated_cost",
                        "confidence","result","order_id","detail"]
                rows = []
                for row in cur.fetchall():
                    d = dict(zip(cols, row))
                    if d["timestamp"]:
                        d["timestamp"] = d["timestamp"].isoformat()
                    for k in ("price","estimated_cost"):
                        if d[k] is not None:
                            d[k] = float(d[k])
                    rows.append(d)
                return rows
    except Exception as e:
        logger.error(f"db_get_trades error: {e}")
        return None


def db_insert_trade(row: dict) -> None:
    """Insert a trade row. Called from execution.py when DB is configured."""
    if not is_configured():
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trades
                      (timestamp, symbol, side, qty, price, estimated_cost,
                       confidence, result, order_id, detail)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row.get("timestamp"),
                        row.get("symbol"),
                        row.get("side"),
                        row.get("qty"),
                        row.get("price") or None,
                        row.get("estimated_cost") or None,
                        row.get("confidence"),
                        row.get("result"),
                        row.get("order_id"),
                        row.get("detail"),
                    ),
                )
    except Exception as e:
        logger.error(f"db_insert_trade error: {e}")
