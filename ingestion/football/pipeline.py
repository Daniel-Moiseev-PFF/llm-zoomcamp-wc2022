"""Entrypoint: run the football_ingestion dlt pipeline against Postgres.

Usage: uv run python -m ingestion.football.pipeline
Re-run daily until lineups is fully populated; every run is safe to repeat.
"""

import logging
import os

import dlt
from dlt.destinations.exceptions import DatabaseUndefinedRelation
from dotenv import load_dotenv

from ingestion.football.budget import select_fixtures_to_fetch
from ingestion.football.client import ApiFootballClient
from ingestion.football.resources import (
    DEFAULT_DELAY_SECONDS,
    events,
    fixtures,
    lineups,
    standings,
    teams,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_REQUESTS_PER_RUN = 90  # headroom under ~100/day for the 3 cheap calls


def postgres_credentials() -> str:
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    database = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def create_pipeline() -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name="football_ingestion",
        destination=dlt.destinations.postgres(credentials=postgres_credentials()),
        dataset_name="football",
    )


def _select_id_set(pipeline, table, column) -> set:
    with pipeline.sql_client() as sql:
        qualified = sql.make_qualified_table_name(table)
        query = f"SELECT DISTINCT {column} FROM {qualified}"
        return {row[0] for row in sql.execute_sql(query)}


def get_all_fixture_ids(pipeline) -> set:
    return _select_id_set(pipeline, "fixtures", "fixture__id")


def _loaded_fixture_ids(pipeline, table) -> set:
    try:
        return _select_id_set(pipeline, table, "fixture_id")
    except DatabaseUndefinedRelation:
        # First run: the table doesn't exist yet — nothing loaded.
        return set()


def get_loaded_fixture_ids(pipeline) -> set:
    return _loaded_fixture_ids(pipeline, "lineups")


def get_event_loaded_fixture_ids(pipeline) -> set:
    return _loaded_fixture_ids(pipeline, "events")


def _run_budgeted(pipeline, resource, name, all_ids, loaded_ids, budget, delay_seconds):
    """Fetch one per-fixture resource up to `budget` calls; return calls planned."""
    to_fetch = select_fixtures_to_fetch(all_ids, loaded_ids, budget)
    remaining = len(all_ids - loaded_ids)
    logger.info(
        "%d %s remaining -> fetching %d this run -> ~%d remaining after",
        remaining,
        name,
        len(to_fetch),
        remaining - len(to_fetch),
    )
    if to_fetch:
        pipeline.run(resource(delay_seconds=delay_seconds, fixture_ids=to_fetch))
    return len(to_fetch)


def run(
    client, pipeline, budget: int, delay_seconds: float = DEFAULT_DELAY_SECONDS
) -> None:
    pipeline.run([teams(client), standings(client), fixtures(client)])
    logger.info("Loaded teams, standings, fixtures (3 API calls)")

    all_ids = get_all_fixture_ids(pipeline)
    spent = _run_budgeted(
        pipeline,
        lambda **kw: lineups(client, **kw),
        "lineups",
        all_ids,
        get_loaded_fixture_ids(pipeline),
        budget,
        delay_seconds,
    )
    _run_budgeted(
        pipeline,
        lambda **kw: events(client, **kw),
        "events",
        all_ids,
        get_event_loaded_fixture_ids(pipeline),
        budget - spent,
        delay_seconds,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()
    client = ApiFootballClient(os.environ.get("FOOTBALL_API_KEY", ""))
    budget = int(os.environ.get("MAX_REQUESTS_PER_RUN", DEFAULT_MAX_REQUESTS_PER_RUN))
    run(client, create_pipeline(), budget)


if __name__ == "__main__":
    main()
