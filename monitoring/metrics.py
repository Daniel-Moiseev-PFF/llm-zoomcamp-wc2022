"""Cost accounting for LLM calls.

calculate_cost is copied from llm-zoomcamp 05-monitoring/code/metrics.py;
cost_from_metadata adapts it to run_agent_loop's metadata dict.
"""

from types import SimpleNamespace


def calculate_cost(model, usage):
    cost = 0
    if "gpt-5.4-mini" in model:
        cost = (usage.input_tokens * 0.15 + usage.output_tokens * 0.60) / 1_000_000
    return cost


def cost_from_metadata(model: str, metadata: dict) -> float:
    usage = SimpleNamespace(
        input_tokens=metadata["prompt_tokens"],
        output_tokens=metadata["completion_tokens"],
    )
    return calculate_cost(model, usage)
