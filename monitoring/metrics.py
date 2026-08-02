"""Cost accounting and tool-path classification for agent turns.

calculate_cost is copied from llm-zoomcamp 05-monitoring/code/metrics.py;
cost_from_metadata adapts it to run_agent_loop's metadata dict.
"""

from types import SimpleNamespace

SQL_TOOLS = {"execute_sql"}
# read_section only ever expands a search_prose hit, so it is the prose half too.
PROSE_TOOLS = {"search_prose", "read_section"}


def calculate_cost(model, usage):
    cost = 0
    if "gpt-5.4-mini" in model:
        cost = (usage.input_tokens * 0.15 + usage.output_tokens * 0.60) / 1_000_000
    return cost


def classify_tool_path(tool_calls) -> str:
    """Which half of the knowledge base the agent actually reached.

    The Python counterpart of the tool-path CTE in
    grafana/provisioning/dashboards/wc2026-monitoring.json — the two must agree,
    or the dashboard and the evaluation report will tell different stories about
    the same turn. A turn with no tool calls is 'none' rather than absent,
    matching the CTE's LEFT JOIN LATERAL ... ON TRUE.
    """
    names = {call["name"] for call in tool_calls or []}
    used_sql = bool(names & SQL_TOOLS)
    used_prose = bool(names & PROSE_TOOLS)
    if used_sql and used_prose:
        return "mixed"
    if used_sql:
        return "sql-only"
    if used_prose:
        return "prose-only"
    return "none"


def cost_from_metadata(model: str, metadata: dict) -> float:
    usage = SimpleNamespace(
        input_tokens=metadata["prompt_tokens"],
        output_tokens=metadata["completion_tokens"],
    )
    return calculate_cost(model, usage)
