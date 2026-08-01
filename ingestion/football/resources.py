"""dlt resources for the API-Football World Cup 2026 ingestion."""

import logging
import time

import dlt
import requests

from ingestion.football import LEAGUE_ID, SEASON
from ingestion.football.client import ApiFootballError, RateLimitError

logger = logging.getLogger(__name__)

_LEAGUE_PARAMS = {"league": LEAGUE_ID, "season": SEASON}
_MAX_HONORED_RETRY_AFTER_SECONDS = 60

# The free plan enforces 10 requests/minute on top of the daily cap; 7s spacing
# keeps a long lineups run safely under it.
DEFAULT_DELAY_SECONDS = 7.0


@dlt.resource(name="teams", primary_key="team__id", write_disposition="merge")
def teams(client):
    yield from client.get("/teams", params=_LEAGUE_PARAMS)


@dlt.resource(
    name="standings", primary_key=("team__id", "group"), write_disposition="merge"
)
def standings(client):
    for entry in client.get("/standings", params=_LEAGUE_PARAMS):
        for group_rows in entry["league"]["standings"]:
            yield from group_rows


@dlt.resource(name="fixtures", primary_key="fixture__id", write_disposition="merge")
def fixtures(client):
    yield from client.get("/fixtures", params=_LEAGUE_PARAMS)


def _fetch_for_fixture(client, path, fixture_id):
    """One per-fixture call; on a short per-minute 429, honor Retry-After and retry once."""
    try:
        return client.get(path, params={"fixture": fixture_id})
    except RateLimitError as exc:
        if exc.retry_after and exc.retry_after <= _MAX_HONORED_RETRY_AFTER_SECONDS:
            logger.info(
                "Per-minute rate limit for fixture %s; sleeping %ss and retrying once",
                fixture_id,
                exc.retry_after,
            )
            time.sleep(exc.retry_after)
            return client.get(path, params={"fixture": fixture_id})
        raise


def _per_fixture_records(client, path, fixture_ids, delay_seconds):
    """Fetch one budgeted endpoint per fixture: skip failed fixtures, stop the
    whole run on a rate limit (already-yielded fixtures stay loaded)."""
    for index, fixture_id in enumerate(fixture_ids):
        if index and delay_seconds:
            time.sleep(delay_seconds)
        try:
            records = _fetch_for_fixture(client, path, fixture_id)
        except RateLimitError as exc:
            logger.warning(
                "Rate limit at fixture %s — stopping %s for this run: %s",
                fixture_id,
                path,
                exc,
            )
            break
        except (ApiFootballError, requests.RequestException) as exc:
            logger.warning(
                "Skipping fixture %s (will retry next run): %s", fixture_id, exc
            )
            continue
        for record in records:
            # The API doesn't echo the fixture id back; inject it for the merge
            # key and the resumability check.
            record["fixture_id"] = fixture_id
            yield record


@dlt.resource(
    name="lineups", primary_key=("fixture_id", "team__id"), write_disposition="merge"
)
def lineups(client, fixture_ids, delay_seconds: float = DEFAULT_DELAY_SECONDS):
    yield from _per_fixture_records(
        client, "/fixtures/lineups", fixture_ids, delay_seconds
    )


# Events have no natural per-row key (two identical cards in the same minute are
# legal), so merge on fixture_id alone: a re-load delete-inserts the fixture's
# whole event list.
@dlt.resource(name="events", merge_key="fixture_id", write_disposition="merge")
def events(client, fixture_ids, delay_seconds: float = DEFAULT_DELAY_SECONDS):
    yield from _per_fixture_records(
        client, "/fixtures/events", fixture_ids, delay_seconds
    )
