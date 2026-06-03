"""
SchwabClient base — a requests.Session with the bearer token injected per
request (so a mid-session refresh is picked up automatically), plus a 401
refresh-and-retry-once wrapper.
"""

from __future__ import annotations

import requests
from loguru import logger

from ..auth import SchwabAuth
from ..auth.oauth import TRADER_BASE_URL


class SchwabAPIError(Exception):
    """Raised on a non-2xx Schwab API response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Schwab API {status_code}: {message}")


class _BearerAuth(requests.auth.AuthBase):
    """Injects a fresh bearer token on every request via SchwabAuth."""

    def __init__(self, auth: SchwabAuth):
        self._auth = auth

    def __call__(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        request.headers["Authorization"] = f"Bearer {self._auth.get_valid_token()}"
        return request


class SchwabClient:
    """Base client. `base_url` defaults to the trader API root; market-data
    paths are absolute-from-host so the market-data client overrides as needed."""

    def __init__(self, auth: SchwabAuth | None = None, base_url: str = TRADER_BASE_URL):
        self.auth = auth or SchwabAuth()
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = _BearerAuth(self.auth)
        self.session.headers.update({"Accept": "application/json"})

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        # Market-data paths in the spec start with /marketdata; they live under
        # the api host, not the trader/v1 prefix. Route those from the host root.
        if path.startswith("/marketdata"):
            return "https://api.schwabapi.com" + path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, params=None, json=None, _retried=False):
        url = self._url(path)
        resp = self.session.request(method, url, params=params, json=json, timeout=30)
        if resp.status_code == 401 and not _retried:
            logger.warning("401 from Schwab — refreshing token and retrying once")
            self.auth.refresh()
            return self._request(method, path, params=params, json=json, _retried=True)
        if not (200 <= resp.status_code < 300):
            raise SchwabAPIError(resp.status_code, resp.text[:500])
        return resp

    def get(self, path: str, params: dict | None = None):
        resp = self._request("GET", path, params=params)
        return resp.json() if resp.content else None

    def post(self, path: str, json: dict | None = None):
        return self._request("POST", path, json=json)

    def delete(self, path: str):
        return self._request("DELETE", path)
