from ingestion.football.resources import fixtures, standings, teams
from tests.conftest import table_counts


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
