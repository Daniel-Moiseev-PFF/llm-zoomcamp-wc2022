"""Thin HTTP client for the API-Football v3 REST API."""

import requests

BASE_URL = "https://v3.football.api-sports.io"

# API-Football signals rate limiting inside a 200 body under these error keys.
_RATE_LIMIT_ERROR_KEYS = {"rateLimit", "requests"}


class ApiFootballError(Exception):
    """API-Football returned an error (including 200-with-errors-in-body)."""


class RateLimitError(ApiFootballError):
    """Daily or per-minute request limit reached."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(response):
    value = response.headers.get("Retry-After")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


class ApiFootballClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL, session=None):
        if not api_key:
            raise ApiFootballError("FOOTBALL_API_KEY is missing or empty")
        self._base_url = base_url
        self._session = session if session is not None else requests.Session()
        self._session.headers.update({"x-apisports-key": api_key})

    def get(self, path: str, params: dict | None = None):
        response = self._session.get(
            f"{self._base_url}{path}", params=params, timeout=30
        )
        if response.status_code == 429:
            raise RateLimitError(
                "HTTP 429 from API-Football", retry_after=_parse_retry_after(response)
            )
        response.raise_for_status()
        body = response.json()
        # The API returns errors as [] when empty, dict when populated.
        errors = body.get("errors") or {}
        if errors:
            if isinstance(errors, dict) and _RATE_LIMIT_ERROR_KEYS & errors.keys():
                raise RateLimitError(str(errors))
            raise ApiFootballError(str(errors))
        return body["response"]
