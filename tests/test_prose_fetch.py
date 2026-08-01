import pytest
import requests

from ingestion.prose.fetch import API_URL, WikipediaError, fetch_wikitext
from ingestion.prose.manifest import ARTICLES


class FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_request = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.last_request = (url, params, headers, timeout)
        return self.response


SUCCESS_BODY = {"parse": {"title": "2022 FIFA World Cup", "wikitext": "== Venues ==\nText."}}


def test_fetch_returns_wikitext():
    session = FakeSession(FakeResponse(json_body=SUCCESS_BODY))
    assert fetch_wikitext(1366281110, session=session) == "== Venues ==\nText."


def test_fetch_requests_pinned_revision():
    session = FakeSession(FakeResponse(json_body=SUCCESS_BODY))
    fetch_wikitext(1366281110, session=session)
    url, params, headers, timeout = session.last_request
    assert url == API_URL
    assert params["oldid"] == 1366281110
    assert params["action"] == "parse"
    assert params["prop"] == "wikitext"
    assert "llm-zoomcamp-wc2026" in headers["User-Agent"]
    assert timeout


def test_api_error_body_raises():
    body = {"error": {"code": "nosuchrevid", "info": "There is no revision with ID 1."}}
    session = FakeSession(FakeResponse(json_body=body))
    with pytest.raises(WikipediaError, match="nosuchrevid"):
        fetch_wikitext(1, session=session)


def test_http_error_propagates():
    session = FakeSession(FakeResponse(status_code=500))
    with pytest.raises(requests.HTTPError):
        fetch_wikitext(1366281110, session=session)


def test_manifest_has_five_pinned_articles():
    assert len(ARTICLES) == 5
    assert all(isinstance(a.oldid, int) for a in ARTICLES)
    titles = [a.title for a in ARTICLES]
    assert "2022 FIFA World Cup" in titles
    assert "List of 2022 FIFA World Cup controversies" in titles
