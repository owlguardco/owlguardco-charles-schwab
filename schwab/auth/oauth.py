"""
Schwab OAuth2 flow + token refresh.

The Schwab trader API uses an authorization-code OAuth2 flow. The app key/secret
come from a developer app at developer.schwab.com. Tokens are persisted back to
the .env file (load full dict -> update keys -> rewrite line by line; never sed).

Endpoints (per Schwab developer docs):
  authorize: https://api.schwabapi.com/v1/oauth/authorize
  token:     https://api.schwabapi.com/v1/oauth/token
  trader base: https://api.schwabapi.com/trader/v1

NOTE: validate these against your live developer app — Schwab has revised paths
before. All network calls here are the operator's own authenticated requests.
"""

from __future__ import annotations

import base64
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values
from loguru import logger

AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"

# Refresh when within this many seconds of expiry.
REFRESH_SKEW_SECONDS = 5 * 60

# Repo-root .env (this file is schwab/auth/oauth.py -> parents[2] == repo root).
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"{key} is not set. Add it to {ENV_PATH} (see .env.example)."
        )
    return val


class SchwabAuth:
    """OAuth2 authorization-code flow + token lifecycle for the Schwab trader API."""

    def __init__(self, env_path: Path | str = ENV_PATH):
        self.env_path = Path(env_path)
        self.app_key = _require("SCHWAB_APP_KEY")
        self.app_secret = _require("SCHWAB_APP_SECRET")
        self.callback_url = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

    # ── authorization-code flow ──────────────────────────────────────────────
    def get_auth_url(self) -> str:
        """The URL the operator visits to authorize the app."""
        params = {
            "client_id": self.app_key,
            "redirect_uri": self.callback_url,
            "response_type": "code",
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def _basic_auth_header(self) -> str:
        raw = f"{self.app_key}:{self.app_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def exchange_code(self, redirected_url: str) -> dict:
        """Extract code=... from the URL the operator pasted, exchange it for
        tokens, persist them, and return the token payload."""
        parsed = urllib.parse.urlparse(redirected_url)
        qs = urllib.parse.parse_qs(parsed.query)
        code = (qs.get("code") or [None])[0]
        if not code:
            # Some flows URL-encode the code; fall back to a permissive scan.
            raise RuntimeError(
                "No 'code' parameter found in the redirected URL. Paste the full "
                "URL from the address bar after authorizing (it contains code=...)."
            )
        resp = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.callback_url,
            },
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Token exchange failed: {resp.status_code} {resp.text[:300]}")
        payload = resp.json()
        self._persist_tokens(payload)
        logger.info("Schwab tokens obtained and persisted to {}", self.env_path)
        return payload

    # ── refresh ──────────────────────────────────────────────────────────────
    def refresh(self) -> str:
        """Use the stored refresh token to mint a new access token; persist it."""
        refresh_token = os.environ.get("SCHWAB_REFRESH_TOKEN") or dotenv_values(
            self.env_path
        ).get("SCHWAB_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError(
                "No SCHWAB_REFRESH_TOKEN available. Run scripts/auth_setup.py first."
            )
        resp = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text[:300]}")
        payload = resp.json()
        self._persist_tokens(payload)
        logger.info("Schwab access token refreshed")
        return payload["access_token"]

    def get_valid_token(self) -> str:
        """Return a non-expired access token, refreshing if within the skew window."""
        token = os.environ.get("SCHWAB_ACCESS_TOKEN")
        expiry_raw = os.environ.get("SCHWAB_TOKEN_EXPIRY")
        if not token or not expiry_raw:
            # Fall back to the persisted .env in case the process env is stale.
            vals = dotenv_values(self.env_path)
            token = token or vals.get("SCHWAB_ACCESS_TOKEN")
            expiry_raw = expiry_raw or vals.get("SCHWAB_TOKEN_EXPIRY")
        if not token:
            return self.refresh()
        if expiry_raw:
            try:
                expiry = datetime.fromisoformat(expiry_raw)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry - datetime.now(timezone.utc) <= timedelta(seconds=REFRESH_SKEW_SECONDS):
                    return self.refresh()
            except ValueError:
                return self.refresh()
        return token

    # ── persistence ──────────────────────────────────────────────────────────
    def _persist_tokens(self, payload: dict) -> None:
        """Write access/refresh/expiry back to .env (whole-file rewrite, no sed)."""
        expires_in = int(payload.get("expires_in", 1800))
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        updates = {
            "SCHWAB_ACCESS_TOKEN": payload.get("access_token", ""),
            "SCHWAB_TOKEN_EXPIRY": expiry.isoformat(),
        }
        if payload.get("refresh_token"):
            updates["SCHWAB_REFRESH_TOKEN"] = payload["refresh_token"]
        # Reflect into the live process env too.
        for k, v in updates.items():
            os.environ[k] = v
        self._rewrite_env(updates)

    def _rewrite_env(self, updates: dict) -> None:
        """Load the full .env, update/append keys, write back line by line."""
        lines: list[str] = []
        seen: set[str] = set()
        if self.env_path.exists():
            for line in self.env_path.read_text().splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in line:
                    lines.append(line)
                    continue
                key = line.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                else:
                    lines.append(line)
        for key, val in updates.items():
            if key not in seen:
                lines.append(f"{key}={val}")
        self.env_path.write_text("\n".join(lines) + "\n")
