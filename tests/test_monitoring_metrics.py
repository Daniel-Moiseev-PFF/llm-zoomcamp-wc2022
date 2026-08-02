from types import SimpleNamespace

from monitoring.metrics import calculate_cost, classify_tool_path, cost_from_metadata


def calls(*names):
    """run_agent_loop's logged shape."""
    return [{"name": name, "arguments": {}} for name in names]


def test_calculate_cost_gpt_54_mini():
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000)
    assert calculate_cost("gpt-5.4-mini", usage) == 0.15 + 0.60


def test_calculate_cost_unknown_model_is_zero():
    usage = SimpleNamespace(input_tokens=1000, output_tokens=1000)
    assert calculate_cost("some-other-model", usage) == 0


def test_cost_from_metadata_maps_prompt_and_completion_tokens():
    metadata = {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    assert cost_from_metadata("gpt-5.4-mini", metadata) == 0.15
    metadata = {"prompt_tokens": 0, "completion_tokens": 1_000_000}
    assert cost_from_metadata("gpt-5.4-mini", metadata) == 0.60


def test_classify_tool_path_covers_the_four_dashboard_classes():
    assert classify_tool_path(calls("execute_sql")) == "sql-only"
    assert classify_tool_path(calls("search_prose")) == "prose-only"
    assert classify_tool_path(calls("execute_sql", "search_prose")) == "mixed"
    assert classify_tool_path([]) == "none"


def test_read_section_counts_as_prose():
    # It only ever expands a search_prose hit, so on its own it is still the
    # prose half of the knowledge base.
    assert classify_tool_path(calls("read_section")) == "prose-only"
    assert classify_tool_path(calls("execute_sql", "read_section")) == "mixed"


def test_repeated_calls_to_one_tool_do_not_change_the_path():
    # The agent retries its own bad SQL; two execute_sql calls are still sql-only.
    assert classify_tool_path(calls("execute_sql", "execute_sql")) == "sql-only"


def test_no_tool_calls_is_none_not_missing():
    # Matches the dashboard's LEFT JOIN LATERAL ... ON TRUE: a turn answered or
    # declined without a tool is its own class, not an absent row.
    assert classify_tool_path(None) == "none"
