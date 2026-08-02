from types import SimpleNamespace

from evaluation.ground_truth import (
    GROUND_TRUTH_INSTRUCTIONS,
    MIN_CONTENT_CHARS,
    GeneratedQuestions,
    generate_for_chunk,
    rows_for_chunks,
)


class FakeParses:
    """client.responses.parse: each scripted item is (parsed, usage) or raises."""

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


def usage(input_tokens=100, output_tokens=50):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def questions(*items):
    return (GeneratedQuestions(questions=list(items)), usage())


def chunk(content="Argentina beat France on penalties after a 3-3 draw. " * 6, **kw):
    return {
        "article": "2022 FIFA World Cup final",
        "section": "Summary",
        "chunk_index": 0,
        "content": content,
        **kw,
    }


def no_sleep(_seconds):
    pass


def test_the_prompt_carries_the_chunk_content_and_its_section():
    # Section is part of the prompt because it is also weighted 'A' in the
    # lexical index — a question generated blind to it would be scored against
    # a document the arm partly ranks on.
    client = FakeClient([questions("Who won the final?")])
    generate_for_chunk(chunk(), client, "test-model", sleep=no_sleep)
    prompt = client.responses.calls[0]["input"][1]["content"]
    assert "Argentina beat France" in prompt
    assert "Summary" in prompt


def test_rows_carry_the_natural_key_and_the_question():
    client = FakeClient([questions("Who won?", "How did it end?")])
    rows = generate_for_chunk(chunk(), client, "test-model", sleep=no_sleep)
    assert rows == [
        {
            "article": "2022 FIFA World Cup final",
            "section": "Summary",
            "chunk_index": 0,
            "question": "Who won?",
        },
        {
            "article": "2022 FIFA World Cup final",
            "section": "Summary",
            "chunk_index": 0,
            "question": "How did it end?",
        },
    ]


def test_rows_never_carry_the_serial_id():
    # prose.chunks.id is reassigned on every re-ingest; a committed CSV keyed on
    # it would silently start scoring against different chunks.
    client = FakeClient([questions("Who won?")])
    rows = generate_for_chunk(chunk(id=4171), client, "test-model", sleep=no_sleep)
    assert "id" not in rows[0]


def test_per_chunk_is_requested_in_the_prompt():
    client = FakeClient([questions("a", "b")])
    generate_for_chunk(chunk(), client, "test-model", per_chunk=2, sleep=no_sleep)
    assert "2" in client.responses.calls[0]["input"][1]["content"]


def test_the_structured_output_type_is_the_questions_model():
    client = FakeClient([questions("a")])
    generate_for_chunk(chunk(), client, "test-model", sleep=no_sleep)
    assert client.responses.calls[0]["text_format"] is GeneratedQuestions


def test_short_chunks_are_skipped_without_spending_a_call():
    # A one-line stub section cannot support a question that identifies it.
    client = FakeClient([])
    rows = rows_for_chunks([chunk(content="x" * (MIN_CONTENT_CHARS - 1))], client, "m")
    assert rows == []
    assert client.responses.calls == []


def test_a_failing_chunk_is_skipped_without_losing_the_rest_of_the_run():
    # 208 chunks in; one bad response must not cost the other 207.
    client = FakeClient([RuntimeError("bad json")] * 3 + [questions("Who won?")])
    rows = rows_for_chunks(
        [chunk(chunk_index=0), chunk(chunk_index=1)], client, "m", sleep=no_sleep
    )
    assert [r["chunk_index"] for r in rows] == [1]


def test_every_chunk_that_works_contributes_its_questions():
    client = FakeClient([questions("a"), questions("b", "c")])
    rows = rows_for_chunks(
        [chunk(chunk_index=0), chunk(chunk_index=1)], client, "m", sleep=no_sleep
    )
    assert [r["question"] for r in rows] == ["a", "b", "c"]


def test_the_instructions_tell_the_model_not_to_copy_the_wording():
    # Without this the generated questions echo the chunk, and the lexical arm
    # wins the comparison by construction rather than on merit.
    assert "as few words as possible" in GROUND_TRUTH_INSTRUCTIONS


def test_the_instructions_describe_this_domain():
    lowered = GROUND_TRUTH_INSTRUCTIONS.lower()
    assert "world cup" in lowered
