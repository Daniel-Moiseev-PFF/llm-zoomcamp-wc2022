from ingestion.football.pipeline import (
    get_all_fixture_ids,
    get_event_loaded_fixture_ids,
    get_loaded_fixture_ids,
    run,
)
from tests.conftest import table_counts


def test_first_run_loads_everything_within_budget(fake_client, duckdb_pipeline):
    run(fake_client, duckdb_pipeline, budget=90, delay_seconds=0)
    counts = table_counts(
        duckdb_pipeline, "teams", "standings", "fixtures", "lineups", "events"
    )
    assert counts == {
        "teams": 2, "standings": 3, "fixtures": 2, "lineups": 4, "events": 4
    }


def test_loaded_fixture_ids_empty_before_lineups_table_exists(
    fake_client, duckdb_pipeline
):
    # Only load fixtures — the lineups and events tables don't exist yet.
    from ingestion.football.resources import fixtures

    duckdb_pipeline.run(fixtures(fake_client))
    assert get_loaded_fixture_ids(duckdb_pipeline) == set()
    assert get_event_loaded_fixture_ids(duckdb_pipeline) == set()
    assert get_all_fixture_ids(duckdb_pipeline) == {1001, 1002}


def test_budget_caps_lineup_calls_and_resumes_next_run(fake_client, duckdb_pipeline):
    run(fake_client, duckdb_pipeline, budget=1, delay_seconds=0)
    assert fake_client.lineup_call_count() == 1
    assert fake_client.event_call_count() == 0  # lineups exhausted the budget
    assert get_loaded_fixture_ids(duckdb_pipeline) == {1001}  # lowest id first

    run(fake_client, duckdb_pipeline, budget=1, delay_seconds=0)
    assert fake_client.lineup_call_count() == 2
    assert get_loaded_fixture_ids(duckdb_pipeline) == {1001, 1002}


def test_events_get_leftover_budget_after_lineups(fake_client, duckdb_pipeline):
    run(fake_client, duckdb_pipeline, budget=3, delay_seconds=0)
    assert fake_client.lineup_call_count() == 2
    assert fake_client.event_call_count() == 1  # 3 - 2 lineups = 1 left for events
    assert get_event_loaded_fixture_ids(duckdb_pipeline) == {1001}

    run(fake_client, duckdb_pipeline, budget=3, delay_seconds=0)
    assert fake_client.lineup_call_count() == 2  # lineups complete: no new calls
    assert get_event_loaded_fixture_ids(duckdb_pipeline) == {1001, 1002}


def test_fully_loaded_run_makes_no_expensive_calls(fake_client, duckdb_pipeline):
    run(fake_client, duckdb_pipeline, budget=90, delay_seconds=0)
    lineup_calls = fake_client.lineup_call_count()
    event_calls = fake_client.event_call_count()
    run(fake_client, duckdb_pipeline, budget=90, delay_seconds=0)
    assert fake_client.lineup_call_count() == lineup_calls  # no-op on expensive endpoints
    assert fake_client.event_call_count() == event_calls
    counts = table_counts(
        duckdb_pipeline, "teams", "standings", "fixtures", "lineups", "events"
    )
    assert counts == {
        "teams": 2, "standings": 3, "fixtures": 2, "lineups": 4, "events": 4
    }
