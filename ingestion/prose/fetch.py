"""Fetch article wikitext from the MediaWiki Action API by pinned revision id."""

import requests

API_URL = "https://en.wikipedia.org/w/api.php"
# Wikimedia etiquette: identify the client and give a contact address.
USER_AGENT = "llm-zoomcamp-wc2026/0.1 (mosesibnmoses@gmail.com)"
TIMEOUT_SECONDS = 30


class WikipediaError(Exception):
    pass


def fetch_wikitext(oldid: int, session=None) -> str:
    session = session or requests.Session()
    response = session.get(
        API_URL,
        params={
            "action": "parse",
            "oldid": oldid,
            "prop": "wikitext",
            "format": "json",
            "formatversion": 2,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise WikipediaError(str(body["error"]))
    return body["parse"]["wikitext"]
