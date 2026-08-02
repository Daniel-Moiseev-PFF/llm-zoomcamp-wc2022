from types import SimpleNamespace

from evaluation.judge_offline import (
    MISSING_VERDICT,
    AnswerVerdict,
    JUDGE_INSTRUCTIONS,
    judge_answer,
    judge_or_missing,
    summarise,
)
from monitoring.metrics import calculate_cost

MODEL = "gpt-5.4-mini"


class FakeParses:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def parse(self, model, input, text_format):
        self.calls.append(
            {"model": model, "input": list(input), "text_format": text_format}
        )
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        parsed, usage = item
        return SimpleNamespace(output_parsed=parsed, usage=usage)


class FakeClient:
    def __init__(self, scripted):
        self.responses = FakeParses(scripted)


def usage(input_tokens=1000, output_tokens=100):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def scored(verdict="CORRECT", explanation="Matches the reference."):
    return (AnswerVerdict(verdict=verdict, explanation=explanation), usage())


def no_sleep(_seconds):
    pass


def test_the_prompt_carries_the_question_the_reference_and_the_answer():
    # This is the whole difference from the online judge, which never sees a
    # reference: here the judge scores correctness, not topical relevance.
    client = FakeClient([scored()])
    judge_answer(
        "Who won the final?",
        "Argentina, 4-2 on penalties.",
        "Argentina beat France on penalties.",
        client=client,
        sleep=no_sleep,
    )
    prompt = client.responses.calls[0]["input"][1]["content"]
    assert "Who won the final?" in prompt
    assert "4-2 on penalties" in prompt
    assert "Argentina beat France" in prompt


def test_the_structured_output_type_is_the_answer_verdict():
    client = FakeClient([scored()])
    judge_answer("q", "ref", "ans", client=client, sleep=no_sleep)
    assert client.responses.calls[0]["text_format"] is AnswerVerdict


def test_the_verdict_reports_what_the_judge_call_cost():
    client = FakeClient([scored()])
    result = judge_answer("q", "ref", "ans", client=client, model=MODEL, sleep=no_sleep)
    assert result.cost == calculate_cost(MODEL, usage())
    assert result.verdict == "CORRECT"
    assert result.explanation == "Matches the reference."


def test_a_permanently_failing_judge_yields_a_missing_verdict_not_an_exception():
    # Dropping the row instead would let a variant look better precisely
    # because its hardest answers failed to score.
    client = FakeClient([RuntimeError("api down")] * 3)
    result = judge_or_missing("q", "ref", "ans", client=client, sleep=no_sleep)
    assert result.verdict == MISSING_VERDICT
    assert result.cost == 0.0


def test_a_recovered_judge_still_returns_a_real_verdict():
    client = FakeClient([RuntimeError("flaky"), scored("PARTLY_CORRECT")])
    result = judge_or_missing("q", "ref", "ans", client=client, sleep=no_sleep)
    assert result.verdict == "PARTLY_CORRECT"


def test_the_instructions_describe_all_three_labels():
    for label in ("CORRECT", "PARTLY_CORRECT", "INCORRECT"):
        assert label in JUDGE_INSTRUCTIONS


def test_the_instructions_say_a_correct_decline_is_correct():
    # Off-topic rows carry "the system should decline" as their reference, so a
    # decline has to be scorable as right — the opposite of the online judge.
    lowered = JUDGE_INSTRUCTIONS.lower()
    assert "decline" in lowered


def test_summarise_counts_verdicts_per_variant():
    rows = [
        {"variant": "full", "verdict": "CORRECT", "cost": "0.001",
         "total_tokens": "1000", "response_time": "2.0", "actual_path": "sql-only",
         "expected_path": "sql-only"},
        {"variant": "full", "verdict": "INCORRECT", "cost": "0.001",
         "total_tokens": "2000", "response_time": "4.0", "actual_path": "none",
         "expected_path": "sql-only"},
        {"variant": "lean", "verdict": "CORRECT", "cost": "0.002",
         "total_tokens": "1000", "response_time": "2.0", "actual_path": "sql-only",
         "expected_path": "sql-only"},
    ]
    summary = {row["variant"]: row for row in summarise(rows)}
    assert summary["full"]["CORRECT"] == 1
    assert summary["full"]["INCORRECT"] == 1
    assert summary["full"]["answers"] == 2
    assert summary["lean"]["correct_share"] == 1.0
    assert summary["full"]["mean_tokens"] == 1500
    assert summary["full"]["routed_as_expected"] == 1


def test_summarise_reports_missing_verdicts_instead_of_hiding_them():
    rows = [
        {"variant": "full", "verdict": "CORRECT", "cost": "0.001",
         "total_tokens": "1000", "response_time": "2.0", "actual_path": "none",
         "expected_path": "none"},
        {"variant": "full", "verdict": MISSING_VERDICT, "cost": "0.0",
         "total_tokens": "1000", "response_time": "2.0", "actual_path": "none",
         "expected_path": "none"},
    ]
    summary = summarise(rows)[0]
    assert summary[MISSING_VERDICT] == 1
    # A verdict that never arrived is not evidence of a correct answer.
    assert summary["correct_share"] == 0.5
