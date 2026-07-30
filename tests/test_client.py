import pytest
import requests

from ingestion.football.client import ApiFootballClient, ApiFootballError, RateLimitError


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, headers=None):
        self.status_code = status_code
        self._json = json_body or {}
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.last_request = None

    def get(self, url, params=None, timeout=None):
        self.last_request = (url, params, timeout)
        return self.response


def make_client(response):
    session = FakeSession(response)
    client = ApiFootballClient("test-key", session=session)
    return client, session


SUCCESS_BODY = {
    "get": "teams",
    "parameters": {"league": "1", "season": "2026"},
    "errors": [],
    "results": 1,
    "response": [{"team": {"id": 25, "name": "Germany"}}],
}


def test_get_returns_response_list_on_success():
    client, session = make_client(FakeResponse(json_body=SUCCESS_BODY))
    result = client.get("/teams", params={"league": 1, "season": 2026})
    assert result == [{"team": {"id": 25, "name": "Germany"}}]
    url, params, timeout = session.last_request
    assert url.endswith("/teams")
    assert params == {"league": 1, "season": 2026}


def test_api_key_header_is_set():
    client, session = make_client(FakeResponse(json_body=SUCCESS_BODY))
    assert session.headers["x-apisports-key"] == "test-key"


def test_missing_api_key_raises():
    with pytest.raises(ApiFootballError):
        ApiFootballClient("")


def test_errors_in_200_body_raises_api_error():
    body = {"errors": {"token": "Error/Missing application key."}, "response": []}
    client, _ = make_client(FakeResponse(json_body=body))
    with pytest.raises(ApiFootballError):
        client.get("/teams")


def test_daily_rate_limit_in_body_raises_rate_limit_error():
    body = {
        "errors": {"requests": "You have reached the request limit for the day."},
        "response": [],
    }
    client, _ = make_client(FakeResponse(json_body=body))
    with pytest.raises(RateLimitError):
        client.get("/fixtures/lineups", params={"fixture": 1})


def test_http_429_raises_rate_limit_error_with_retry_after():
    client, _ = make_client(FakeResponse(status_code=429, headers={"Retry-After": "17"}))
    with pytest.raises(RateLimitError) as exc_info:
        client.get("/teams")
    assert exc_info.value.retry_after == 17


def test_http_error_propagates():
    client, _ = make_client(FakeResponse(status_code=500))
    with pytest.raises(requests.HTTPError):
        client.get("/teams")
