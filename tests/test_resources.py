import requests

from ingestion.football.client import ApiFootballError, RateLimitError
from ingestion.football.resources import fixtures, lineups, standings, teams
from tests.conftest import FakeClient, table_counts


def test_teams_load_and_merge_idempotency(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(teams(fake_client))
    duckdb_pipeline.run(teams(fake_client))
    assert table_counts(duckdb_pipeline, "teams")["teams"] == 2


def test_teams_flatten_venue_columns(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(teams(fake_client))
    with duckdb_pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name("teams")
        rows = client.execute_sql(
            f"SELECT team__id, team__name, venue__name, venue__capacity "
            f"FROM {qualified} ORDER BY team__id"
        )
    assert rows[0][:2] == (25, "Germany")
    assert rows[0][2] == "Estadio Azteca"
    assert rows[0][3] == 87523


def test_standings_one_row_per_team_per_group(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(standings(fake_client))
    duckdb_pipeline.run(standings(fake_client))
    # 2 teams in Group A + 1 in Group B, no duplication on re-run
    assert table_counts(duckdb_pipeline, "standings")["standings"] == 3


def test_standings_flatten_stats(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(standings(fake_client))
    with duckdb_pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name("standings")
        rows = client.execute_sql(
            f'SELECT team__id, "group", points, all__played, all__goals__for '
            f"FROM {qualified} ORDER BY \"group\", rank"
        )
    assert rows[0] == (25, "Group A", 9, 3, 7)


def test_fixtures_load_and_merge_idempotency(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(fixtures(fake_client))
    duckdb_pipeline.run(fixtures(fake_client))
    assert table_counts(duckdb_pipeline, "fixtures")["fixtures"] == 2


def test_fixtures_have_teams_and_score(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(fixtures(fake_client))
    with duckdb_pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name("fixtures")
        rows = client.execute_sql(
            f"SELECT fixture__id, teams__home__id, teams__away__id, goals__home "
            f"FROM {qualified} ORDER BY fixture__id"
        )
    assert rows[0] == (1001, 25, 26, 2)


def test_cheap_resources_make_one_call_each(fake_client, duckdb_pipeline):
    duckdb_pipeline.run([teams(fake_client), standings(fake_client), fixtures(fake_client)])
    assert len(fake_client.calls) == 3


def test_lineups_two_rows_per_fixture_with_injected_fixture_id(
    fake_client, duckdb_pipeline
):
    duckdb_pipeline.run(lineups(fake_client, [1001, 1002], delay_seconds=0))
    with duckdb_pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name("lineups")
        rows = client.execute_sql(
            f"SELECT fixture_id, team__id FROM {qualified} ORDER BY fixture_id, team__id"
        )
    assert rows == [(1001, 25), (1001, 26), (1002, 25), (1002, 27)]


def test_lineups_merge_idempotency_including_child_tables(fake_client, duckdb_pipeline):
    duckdb_pipeline.run(lineups(fake_client, [1001, 1002], delay_seconds=0))
    first = table_counts(
        duckdb_pipeline, "lineups", "lineups__start_xi", "lineups__substitutes"
    )
    duckdb_pipeline.run(lineups(FakeClient(), [1001, 1002], delay_seconds=0))
    second = table_counts(
        duckdb_pipeline, "lineups", "lineups__start_xi", "lineups__substitutes"
    )
    assert first == {"lineups": 4, "lineups__start_xi": 8, "lineups__substitutes": 4}
    assert second == first


def test_lineups_self_join_answers_played_against(fake_client, duckdb_pipeline):
    # The README question: did player 101 (Germany) and 201 (Scotland) play
    # against each other? Fixture 1001 should match via the child-table self-join.
    duckdb_pipeline.run(lineups(fake_client, [1001, 1002], delay_seconds=0))
    with duckdb_pipeline.sql_client() as client:
        l = client.make_qualified_table_name("lineups")
        sx = client.make_qualified_table_name("lineups__start_xi")
        rows = client.execute_sql(
            f"""
            SELECT DISTINCT a_parent.fixture_id
            FROM {sx} a
            JOIN {l} a_parent ON a._dlt_parent_id = a_parent._dlt_id
            JOIN {l} b_parent ON b_parent.fixture_id = a_parent.fixture_id
                AND b_parent.team__id != a_parent.team__id
            JOIN {sx} b ON b._dlt_parent_id = b_parent._dlt_id
            WHERE a.player__id = 101 AND b.player__id = 201
            """
        )
    assert rows == [(1001,)]


def test_lineups_skips_failed_fixture_and_continues(duckdb_pipeline):
    client = FakeClient(lineup_errors={1001: ApiFootballError("boom")})
    duckdb_pipeline.run(lineups(client, [1001, 1002], delay_seconds=0))
    assert client.lineup_call_count() == 2  # tried both despite first failing
    with duckdb_pipeline.sql_client() as sql:
        qualified = sql.make_qualified_table_name("lineups")
        rows = sql.execute_sql(f"SELECT DISTINCT fixture_id FROM {qualified}")
    assert rows == [(1002,)]


def test_lineups_network_error_is_skipped_too(duckdb_pipeline):
    client = FakeClient(lineup_errors={1001: requests.ConnectionError("timeout")})
    duckdb_pipeline.run(lineups(client, [1001, 1002], delay_seconds=0))
    assert client.lineup_call_count() == 2


def test_lineups_rate_limit_stops_the_loop(duckdb_pipeline):
    client = FakeClient(lineup_errors={1001: RateLimitError("daily limit")})
    duckdb_pipeline.run(lineups(client, [1001, 1002], delay_seconds=0))
    assert client.lineup_call_count() == 1  # broke out, never tried 1002


def test_lineups_retries_once_on_429_with_retry_after(duckdb_pipeline, monkeypatch):
    sleeps = []
    monkeypatch.setattr("ingestion.football.resources.time.sleep", sleeps.append)

    class RetryOnceClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.failed_once = False

        def get(self, path, params=None):
            if path == "/fixtures/lineups" and not self.failed_once:
                self.failed_once = True
                self.calls.append((path, params))
                raise RateLimitError("per-minute limit", retry_after=3)
            return super().get(path, params)

    client = RetryOnceClient()
    duckdb_pipeline.run(lineups(client, [1001], delay_seconds=0))
    assert 3 in sleeps  # honored Retry-After
    with duckdb_pipeline.sql_client() as sql:
        qualified = sql.make_qualified_table_name("lineups")
        assert sql.execute_sql(f"SELECT count(*) FROM {qualified}")[0][0] == 2
