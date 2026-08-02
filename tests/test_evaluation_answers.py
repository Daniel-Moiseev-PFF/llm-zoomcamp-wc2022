import csv
import json

from evaluation.answers import (
    FIELDNAMES,
    existing_keys,
    load_runs,
    run_variant,
    write_csv,
)
from evaluation.variants import VARIANTS
from monitoring.metrics import cost_from_metadata

MODEL = "gpt-5.4-mini"

QUESTIONS = [
    {"id": "q1", "question": "Who won the final?", "path": "sql-only"},
    {"id": "q2", "question": "What was the biggest scandal?", "path": "prose-only"},
]


def metadata(tools=(), prompt=1000, completion=200, response_time=2.5, iterations=2):
    return {
        "model_used": MODEL,
        "response_time": response_time,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "tool_calls": [{"name": name, "arguments": {}} for name in tools],
        "iterations": iterations,
    }


class FakeLoop:
    """Stands in for run_agent_loop: each scripted item is (answer, metadata) or raises."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def __call__(
        self, client, model, tools, tool_schemas, question, history=None, instructions=None
    ):
        self.calls.append({"question": question, "instructions": instructions})
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        answer, meta = item
        return answer, [], meta


def answered(text="Argentina.", tools=("execute_sql",), **kw):
    return (text, metadata(tools=tools, **kw))


def run(scripted, variant="full", questions=QUESTIONS, existing=()):
    loop = FakeLoop(scripted)
    rows = run_variant(
        variant, questions, client=None, model=MODEL, tools={}, tool_schemas=[],
        existing=existing, loop=loop,
    )
    return rows, loop


def test_every_question_runs_under_the_variants_own_instructions():
    _, loop = run([answered(), answered()], variant="lean")
    assert [c["question"] for c in loop.calls] == [q["question"] for q in QUESTIONS]
    assert {c["instructions"] for c in loop.calls} == {VARIANTS["lean"]}


def test_a_question_already_run_for_this_variant_is_skipped():
    # 90 runs is about six minutes; a crash must not cost the whole set.
    rows, loop = run([answered()], existing={("full", "q1")})
    assert [c["question"] for c in loop.calls] == ["What was the biggest scandal?"]
    assert [r["id"] for r in rows] == ["q2"]


def test_the_same_question_still_runs_for_a_different_variant():
    _, loop = run([answered(), answered()], variant="lean", existing={("full", "q1")})
    assert len(loop.calls) == 2


def test_a_failing_question_leaves_no_row_and_does_not_abort_the_run():
    # No row means the next invocation retries it, rather than banking a blank.
    rows, loop = run([RuntimeError("api down"), answered("Qatar.")])
    assert len(loop.calls) == 2
    assert [r["id"] for r in rows] == ["q2"]


def test_the_row_records_the_path_the_agent_actually_took():
    rows, _ = run([answered(tools=("execute_sql", "search_prose")), answered()])
    assert rows[0]["expected_path"] == "sql-only"
    assert rows[0]["actual_path"] == "mixed"


def test_all_four_tool_paths_classify():
    questions = [{"id": f"q{i}", "question": f"Q{i}", "path": "none"} for i in range(4)]
    scripted = [
        answered(tools=("execute_sql",)),
        answered(tools=("search_prose",)),
        answered(tools=("execute_sql", "read_section")),
        answered(tools=()),
    ]
    rows, _ = run(scripted, questions=questions)
    assert [r["actual_path"] for r in rows] == [
        "sql-only",
        "prose-only",
        "mixed",
        "none",
    ]


def test_the_row_carries_the_answer_tokens_and_derived_cost():
    rows, _ = run([answered("Argentina won.", prompt=1000, completion=200), answered()])
    row = rows[0]
    assert row["answer"] == "Argentina won."
    assert row["total_tokens"] == 1200 == row["prompt_tokens"] + row["completion_tokens"]
    assert row["cost"] == cost_from_metadata(MODEL, metadata(prompt=1000, completion=200))


def test_an_agent_that_never_answered_records_an_empty_answer_not_a_crash():
    # run_agent_loop returns None at the iteration cap.
    rows, _ = run([(None, metadata()), answered()])
    assert rows[0]["answer"] == ""


def test_tool_calls_are_recorded_in_order():
    rows, _ = run([answered(tools=("search_prose", "read_section")), answered()])
    assert json.loads(rows[0]["tool_calls"]) == ["search_prose", "read_section"]


def test_runs_round_trip_through_the_csv(tmp_path):
    path = tmp_path / "answer-runs.csv"
    rows, _ = run([answered(), answered()])
    write_csv(rows, path)
    written = list(csv.DictReader(path.open(encoding="utf-8")))
    assert set(written[0]) == set(FIELDNAMES)
    assert existing_keys(load_runs(path)) == {("full", "q1"), ("full", "q2")}


def test_load_runs_is_empty_when_nothing_has_been_run_yet(tmp_path):
    assert load_runs(tmp_path / "missing.csv") == []
