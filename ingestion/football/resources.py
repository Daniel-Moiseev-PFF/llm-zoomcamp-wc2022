"""dlt resources for the API-Football World Cup 2026 ingestion."""

import logging

import dlt

from ingestion.football import LEAGUE_ID, SEASON

logger = logging.getLogger(__name__)

_LEAGUE_PARAMS = {"league": LEAGUE_ID, "season": SEASON}


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
