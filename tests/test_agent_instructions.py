from agent.instructions import INSTRUCTIONS
from agent.tools import TOOL_SCHEMAS


def test_schema_reference_covers_football_tables():
    for table in (
        "football.teams",
        "football.standings",
        "football.fixtures",
        "football.lineups",
        "football.lineups__start_xi",
        "football.lineups__substitutes",
    ):
        assert table in INSTRUCTIONS


def test_child_table_join_key_is_documented():
    assert "_dlt_parent_id" in INSTRUCTIONS
    assert "_dlt_id" in INSTRUCTIONS


def test_every_tool_is_mentioned_by_name():
    for schema in TOOL_SCHEMAS:
        assert schema["name"] in INSTRUCTIONS
