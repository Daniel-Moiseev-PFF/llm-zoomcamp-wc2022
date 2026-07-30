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


def _select_id_set(pipeline, query_template) -> set:
    with pipeline.sql_client() as sql:
        fixtures_table = sql.make_qualified_table_name("fixtures")
        lineups_table = sql.make_qualified_table_name("lineups")
        query = query_template.format(fixtures=fixtures_table, lineups=lineups_table)
        return {row[0] for row in sql.execute_sql(query)}


def get_all_fixture_ids(pipeline) -> set:
    return _select_id_set(pipeline, "SELECT fixture__id FROM {fixtures}")


def get_loaded_fixture_ids(pipeline) -> set:
    try:
        return _select_id_set(pipeline, "SELECT DISTINCT fixture_id FROM {lineups}")
    except DatabaseUndefinedRelation:
        # First run: the lineups table doesn't exist yet — nothing loaded.
        return set()


def run(
    client, pipeline, budget: int, delay_seconds: float = DEFAULT_DELAY_SECONDS
) -> None:
    pipeline.run([teams(client), standings(client), fixtures(client)])
    logger.info("Loaded teams, standings, fixtures (3 API calls)")

    all_ids = get_all_fixture_ids(pipeline)
    loaded_ids = get_loaded_fixture_ids(pipeline)
    to_fetch = select_fixtures_to_fetch(all_ids, loaded_ids, budget)
    remaining = len(all_ids - loaded_ids)
    logger.info(
        "%d lineups remaining -> fetching %d this run -> ~%d remaining after",
        remaining,
        len(to_fetch),
        remaining - len(to_fetch),
    )
    if to_fetch:
        pipeline.run(lineups(client, to_fetch, delay_seconds=delay_seconds))


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
