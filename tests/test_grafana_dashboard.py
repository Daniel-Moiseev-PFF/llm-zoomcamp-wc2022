"""The dashboard is committed, so it can be checked like any other source file.

These tests never start Grafana or touch Postgres — they read the provisioning
files and assert the things that silently break a provisioned dashboard.
"""

import json
from pathlib import Path

import pytest
import yaml

PROVISIONING = Path(__file__).resolve().parent.parent / "grafana" / "provisioning"
DASHBOARD_PATH = PROVISIONING / "dashboards" / "wc2026-monitoring.json"
DATASOURCE_PATH = PROVISIONING / "datasources" / "postgres.yml"

# The README's Monitoring section promises these charts.
REQUIRED_CHARTS = {
    "Feedback rate",
    "Response time",
    "Cost — agent vs judge",
    "Tokens",
    "Judge relevance",
    "Tool routing",
    "Feedback by tool path",
}


@pytest.fixture(scope="module")
def dashboard():
    return json.loads(DASHBOARD_PATH.read_text())


@pytest.fixture(scope="module")
def datasource():
    return yaml.safe_load(DATASOURCE_PATH.read_text())["datasources"][0]


def queries(dashboard):
    return [
        target["rawSql"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    ]


def test_dashboard_has_at_least_five_charts(dashboard):
    assert len(dashboard["panels"]) >= 5


def test_the_promised_charts_are_all_there(dashboard):
    assert REQUIRED_CHARTS <= {panel["title"] for panel in dashboard["panels"]}


def test_every_panel_points_at_the_provisioned_datasource(dashboard, datasource):
    # A uid mismatch is the classic provisioning break: every panel renders
    # "datasource not found" and nothing else looks wrong.
    uid = datasource["uid"]
    for panel in dashboard["panels"]:
        assert panel["datasource"]["uid"] == uid
        for target in panel["targets"]:
            assert target["datasource"]["uid"] == uid


def test_the_dashboard_has_a_stable_uid(dashboard):
    # Re-provisioning updates in place rather than creating duplicates.
    assert dashboard["uid"]
    assert dashboard["id"] is None


def test_every_query_is_schema_qualified(dashboard):
    for sql in queries(dashboard):
        assert "monitoring." in sql
        assert "FROM conversations" not in sql  # the course's unqualified form
        assert "FROM feedback" not in sql


def test_every_query_honours_the_dashboard_time_range(dashboard):
    for sql in queries(dashboard):
        assert "$__timeFrom()" in sql
        assert "$__timeTo()" in sql


def test_every_query_is_read_only(dashboard):
    for sql in queries(dashboard):
        upper = sql.upper()
        for statement in ("INSERT", "UPDATE ", "DELETE", "DROP", "ALTER", "TRUNCATE"):
            assert statement not in upper


def test_user_feedback_queries_count_only_the_latest_thumb(dashboard):
    # app/main.py inserts a new row each time a thumb changes, so a flip from
    # 👎 to 👍 would otherwise be counted on both sides. Every query reading user
    # feedback has to reduce to one row per conversation, whether by DISTINCT ON
    # or by a lateral LIMIT 1.
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            sql = target["rawSql"]
            if "source = 'user'" in sql:
                assert "DISTINCT ON" in sql or "LIMIT 1" in sql, panel["title"]
                assert "ORDER BY" in sql and "timestamp DESC" in sql, panel["title"]


def test_datasource_reaches_postgres_over_the_compose_network(datasource):
    assert datasource["url"] == "postgres:5432"  # the service name, not localhost
    assert datasource["jsonData"]["sslmode"] == "disable"


def test_datasource_credentials_come_from_the_environment(datasource):
    assert datasource["secureJsonData"]["password"] == "$POSTGRES_PASSWORD"
    assert datasource["user"] == "$POSTGRES_USER"
