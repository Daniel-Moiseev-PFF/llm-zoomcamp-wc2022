import json
from types import SimpleNamespace

from agent.tools import MAX_ROWS, TOOL_SCHEMAS, execute_sql, make_call, read_section


class FakeCursor:
    def __init__(self, columns, rows, error=None):
        self.description = [SimpleNamespace(name=c) for c in columns]
        self._rows = rows
        self._error = error
        self.executed = None

    def execute(self, query, params=None):
        if self._error:
            raise self._error
        self.executed = (query, params)
        return self

    def fetchmany(self, size):
        return self._rows[:size]

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.read_only = False

    def cursor(self):
        return self._cursor

    def execute(self, query, params=None):
        return self._cursor.execute(query, params)

    def rollback(self):
        pass


def test_execute_sql_returns_columns_and_rows():
    cursor = FakeCursor(["team__name"], [("Argentina",), ("France",)])
    conn = FakeConnection(cursor)
    result = execute_sql(conn, "SELECT team__name FROM football.teams")
    assert result["columns"] == ["team__name"]
    assert result["rows"] == [["Argentina"], ["France"]]
    assert result["row_count"] == 2
    assert "truncated" not in result


def test_execute_sql_caps_rows():
    rows = [(i,) for i in range(MAX_ROWS + 10)]
    conn = FakeConnection(FakeCursor(["n"], rows))
    result = execute_sql(conn, "SELECT n FROM big")
    assert result["row_count"] == MAX_ROWS
    assert result["truncated"] is True


def test_execute_sql_returns_db_error_as_output():
    error = Exception('relation "football.nope" does not exist')
    conn = FakeConnection(FakeCursor([], [], error=error))
    result = execute_sql(conn, "SELECT * FROM football.nope")
    assert "does not exist" in result["error"]


def test_read_section_concatenates_chunks_in_order():
    cursor = FakeCursor(["content"], [("First paragraph.",), ("Second paragraph.",)])
    conn = FakeConnection(cursor)
    result = read_section(conn, "2022 FIFA World Cup", "Controversies")
    assert result == "First paragraph.\n\nSecond paragraph."


def test_make_call_dispatches_and_wraps_output():
    calls = {}

    def greet(name):
        calls["name"] = name
        return {"hello": name}

    call = SimpleNamespace(name="greet", arguments='{"name": "Ada"}', call_id="c1")
    output = make_call(call, {"greet": greet})
    assert calls["name"] == "Ada"
    assert output["type"] == "function_call_output"
    assert output["call_id"] == "c1"
    assert json.loads(output["output"]) == {"hello": "Ada"}


def test_tool_schemas_cover_all_tools():
    names = {schema["name"] for schema in TOOL_SCHEMAS}
    assert names == {"execute_sql", "search_prose", "read_section"}
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert schema["description"]
