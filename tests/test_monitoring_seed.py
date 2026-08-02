import json
import random
from datetime import datetime, timedelta, timezone

from monitoring.seed import (
    PATH_WEIGHTS,
    SEED_MARKER,
    fake_metadata,
    fake_tool_calls,
    generate_one,
    purge,
    seed_timestamps,
)


class FakeCursor:
    """Records every executed statement on the connection; fetchone is scripted."""

    def __init__(self, conn):
        self._conn = conn
        self.rowcount = 0

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


END = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)


def inserts(conn, table):
    return [
        params
        for query, params in conn.statements
        if f"INSERT INTO monitoring.{table}" in query
    ]


def test_seed_timestamps_honours_the_requested_count():
    stamps = seed_timestamps(END, hours=6, count=40, rng=random.Random(0))
    assert len(stamps) == 40


def test_seed_timestamps_are_ascending_and_inside_the_window():
    stamps = seed_timestamps(END, hours=6, count=40, rng=random.Random(0))
    assert stamps == sorted(stamps)
    assert stamps[0] >= END - timedelta(hours=6)
    assert stamps[-1] <= END


def test_seed_timestamps_are_timezone_aware():
    # A naive timestamp would land the rows in the wrong place on Grafana's axis.
    stamps = seed_timestamps(END, hours=6, count=5, rng=random.Random(0))
    assert all(stamp.tzinfo is not None for stamp in stamps)


def test_fake_tool_calls_cover_every_routing_path():
    rng = random.Random(0)
    seen = {path: set() for path in PATH_WEIGHTS}
    for path in PATH_WEIGHTS:
        for _ in range(50):
            calls = fake_tool_calls(path, rng)
            assert all(
                set(call) == {"name", "arguments"} and isinstance(call["arguments"], dict)
                for call in calls
            )
            seen[path].update(call["name"] for call in calls)

    assert seen["none"] == set()
    assert seen["sql"] == {"execute_sql"}
    assert seen["prose"] == {"search_prose", "read_section"}
    assert seen["mixed"] == {"execute_sql", "search_prose", "read_section"}


def test_fake_metadata_matches_run_agent_loop_shape():
    rng = random.Random(0)
    calls = fake_tool_calls("mixed", rng)
    metadata = fake_metadata("mixed", calls, rng)
    assert set(metadata) == {
        "model_used",
        "response_time",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "tool_calls",
        "iterations",
    }
    assert metadata["total_tokens"] == (
        metadata["prompt_tokens"] + metadata["completion_tokens"]
    )
    assert metadata["response_time"] > 0
    assert metadata["tool_calls"] is calls


def test_generate_one_logs_a_conversation_with_the_given_timestamp():
    conn = FakeConnection(fetchone_result=(1,))
    timestamp = END - timedelta(hours=2)
    generate_one(conn, timestamp, END, random.Random(7))
    (params,) = inserts(conn, "conversations")
    assert params[9] == timestamp
    json.loads(params[8])  # tool_calls goes in as a JSON string, cast to jsonb


def test_seeded_questions_are_marked_as_fabricated():
    conn = FakeConnection(fetchone_result=(1,))
    rng = random.Random(7)
    for stamp in seed_timestamps(END, hours=6, count=30, rng=rng):
        generate_one(conn, stamp, END, rng)
    assert all(
        params[0].startswith(SEED_MARKER) for params in inserts(conn, "conversations")
    )


def test_feedback_lands_after_its_conversation_and_inside_the_window():
    conn = FakeConnection(fetchone_result=(1,))
    rng = random.Random(3)
    timestamp = END - timedelta(minutes=1)  # tight enough to exercise the clamp
    for _ in range(50):
        generate_one(conn, timestamp, END, rng)
    stamps = [params[5] for params in inserts(conn, "feedback")]
    assert stamps  # the run produced feedback at all
    assert all(timestamp <= stamp <= END for stamp in stamps)


def test_a_fixed_seed_produces_identical_traffic():
    def run():
        conn = FakeConnection(fetchone_result=(1,))
        rng = random.Random(42)
        for stamp in seed_timestamps(END, hours=6, count=20, rng=rng):
            generate_one(conn, stamp, END, rng)
        return conn.statements

    assert run() == run()


def test_purge_is_scoped_to_the_marker_and_clears_feedback_first():
    conn = FakeConnection()
    purge(conn)
    tables = [
        "feedback" if "monitoring.feedback" in query else "conversations"
        for query, _ in conn.statements
        if query.strip().startswith("DELETE")
    ]
    assert tables == ["feedback", "conversations"]  # feedback FKs to conversations
    assert all(
        params == (f"{SEED_MARKER}%",)
        for query, params in conn.statements
        if query.strip().startswith("DELETE")
    )
