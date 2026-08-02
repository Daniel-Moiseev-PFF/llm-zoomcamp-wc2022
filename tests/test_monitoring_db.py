import json
from datetime import datetime, timedelta, timezone

from monitoring import DB_TIMEZONE
from monitoring.db import init_db, save_conversation, save_feedback


class FakeCursor:
    """Records every executed statement on the connection; fetchone is scripted."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        self._conn.statements.append((query, params))
        return self

    def fetchone(self):
        return self._conn.fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def __init__(self, fetchone_result=None):
        self.statements = []
        self.fetchone_result = fetchone_result
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def execute(self, query, params=None):
        return FakeCursor(self).execute(query, params)

    def commit(self):
        self.commits += 1


METADATA = {
    "model_used": "gpt-5.4-mini",
    "response_time": 2.1,
    "prompt_tokens": 1000,
    "completion_tokens": 234,
    "total_tokens": 1234,
    "tool_calls": [{"name": "execute_sql", "arguments": {"query": "SELECT 1"}}],
    "iterations": 3,
}


def test_init_db_creates_schema_and_tables_idempotently():
    conn = FakeConnection()
    init_db(conn)
    sql = "\n".join(query for query, _ in conn.statements)
    assert "CREATE SCHEMA IF NOT EXISTS monitoring" in sql
    assert "CREATE TABLE IF NOT EXISTS monitoring.conversations" in sql
    assert "CREATE TABLE IF NOT EXISTS monitoring.feedback" in sql
    # This schema holds history — init must never destroy it (course version DROPs).
    assert "DROP" not in sql.upper()
    assert conn.commits >= 1


def test_save_conversation_returns_generated_id():
    conn = FakeConnection(fetchone_result=(7,))
    conversation_id = save_conversation(conn, "Q?", "A.", METADATA, 0.0012)
    assert conversation_id == 7
    assert conn.commits >= 1


def test_save_conversation_param_mapping():
    conn = FakeConnection(fetchone_result=(1,))
    save_conversation(conn, "Q?", "A.", METADATA, 0.0012)
    query, params = conn.statements[-1]
    assert "monitoring.conversations" in query
    assert "RETURNING id" in query
    assert "::jsonb" in query
    params = list(params)
    assert params[:9] == [
        "Q?",
        "A.",
        "gpt-5.4-mini",
        1000,
        234,
        1234,
        2.1,
        0.0012,
        json.dumps(METADATA["tool_calls"]),
    ]
    timestamp = params[9]
    assert isinstance(timestamp, datetime)
    assert timestamp.tzinfo is not None


def test_save_feedback_user_score():
    conn = FakeConnection()
    save_feedback(conn, 7, "user", score=1)
    query, params = conn.statements[-1]
    assert "monitoring.feedback" in query
    params = list(params)
    assert params[:5] == [7, "user", None, None, 1]
    timestamp = params[5]
    assert isinstance(timestamp, datetime)
    assert timestamp.tzinfo is not None
    assert conn.commits >= 1


def test_save_feedback_judge_shape():
    # The later monitoring milestone logs LLM-as-judge verdicts into the same table.
    conn = FakeConnection()
    save_feedback(conn, 7, "judge", relevance="RELEVANT", explanation="On topic.")
    _, params = conn.statements[-1]
    assert list(params)[:5] == [7, "judge", "RELEVANT", "On topic.", None]


def test_init_db_adds_the_judge_cost_column():
    conn = FakeConnection()
    init_db(conn)
    sql = "\n".join(query for query, _ in conn.statements)
    assert "ALTER TABLE monitoring.feedback ADD COLUMN IF NOT EXISTS cost" in sql


def test_init_db_creates_the_indexes_the_dashboard_needs():
    conn = FakeConnection()
    init_db(conn)
    sql = "\n".join(query for query, _ in conn.statements)
    # Every Grafana panel filters on timestamp and joins feedback by conversation.
    assert "CREATE INDEX IF NOT EXISTS conversations_timestamp_idx" in sql
    assert "CREATE INDEX IF NOT EXISTS feedback_conversation_id_idx" in sql
    assert "CREATE INDEX IF NOT EXISTS feedback_timestamp_idx" in sql
    assert "DROP" not in sql.upper()


def test_save_conversation_accepts_an_explicit_timestamp():
    # The seed generator back-dates rows so the dashboard has history to plot.
    conn = FakeConnection(fetchone_result=(1,))
    backdated = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    save_conversation(conn, "Q?", "A.", METADATA, 0.0012, timestamp=backdated)
    _, params = conn.statements[-1]
    assert list(params)[9] == backdated


def test_save_conversation_defaults_the_timestamp_to_now():
    conn = FakeConnection(fetchone_result=(1,))
    save_conversation(conn, "Q?", "A.", METADATA, 0.0012)
    _, params = conn.statements[-1]
    assert abs(list(params)[9] - datetime.now(DB_TIMEZONE)) < timedelta(seconds=5)


def test_save_feedback_accepts_an_explicit_timestamp():
    conn = FakeConnection()
    backdated = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    save_feedback(conn, 7, "user", score=1, timestamp=backdated)
    _, params = conn.statements[-1]
    assert list(params)[5] == backdated


def test_save_feedback_stores_the_judge_cost():
    # The judge is a second LLM call per question; a cost chart that ignores it
    # under-reports by roughly half.
    conn = FakeConnection()
    save_feedback(
        conn, 7, "judge", relevance="RELEVANT", explanation="On topic.", cost=0.00042
    )
    query, params = conn.statements[-1]
    assert "cost" in query
    assert list(params)[6] == 0.00042


def test_save_feedback_cost_is_null_for_a_user_thumb():
    conn = FakeConnection()
    save_feedback(conn, 7, "user", score=-1)
    _, params = conn.statements[-1]
    assert list(params)[6] is None
