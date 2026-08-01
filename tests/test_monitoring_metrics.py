from types import SimpleNamespace

from monitoring.metrics import calculate_cost, cost_from_metadata


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
