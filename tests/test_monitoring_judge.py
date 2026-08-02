from types import SimpleNamespace

import pytest

from monitoring.judge import (
    JUDGE_INSTRUCTIONS,
    RelevanceVerdict,
    evaluate_relevance,
    judge_or_none,
)
from monitoring.llm import llm_structured, llm_structured_retry
from monitoring.metrics import calculate_cost


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


def verdict(relevance="RELEVANT", explanation="On topic."):
    return RelevanceVerdict(relevance=relevance, explanation=explanation)


def usage(input_tokens=300, output_tokens=60):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def test_llm_structured_sends_developer_then_user():
    client = FakeClient([(verdict(), usage())])
    llm_structured(client, "be a judge", "Question: Q?", RelevanceVerdict)
    call = client.responses.calls[0]
    assert call["input"][0] == {"role": "developer", "content": "be a judge"}
    assert call["input"][1] == {"role": "user", "content": "Question: Q?"}
    assert call["text_format"] is RelevanceVerdict


def test_llm_structured_returns_the_parsed_verdict_and_usage():
    parsed, used = verdict(), usage()
    client = FakeClient([(parsed, used)])
    result, returned_usage = llm_structured(client, "i", "p", RelevanceVerdict)
    assert result is parsed
    assert returned_usage is used


def test_llm_structured_retry_retries_then_succeeds():
    sleeps = []
    client = FakeClient([RuntimeError("flaky"), (verdict(), usage())])
    result, _ = llm_structured_retry(
        client, "i", "p", RelevanceVerdict, sleep=sleeps.append
    )
    assert result.relevance == "RELEVANT"
    assert len(client.responses.calls) == 2
    assert sleeps == [1]


def test_llm_structured_retry_raises_after_the_last_attempt():
    sleeps = []
    client = FakeClient([RuntimeError("down")] * 3)
    with pytest.raises(RuntimeError):
        llm_structured_retry(client, "i", "p", RelevanceVerdict, sleep=sleeps.append)
    assert len(client.responses.calls) == 3
    assert sleeps == [1, 2]  # backs off before each retry, not after the last


def test_judge_prompt_carries_the_question_and_the_answer():
    client = FakeClient([(verdict(), usage())])
    evaluate_relevance("Who refereed the final?", "Szymon Marciniak.", client=client)
    user_message = client.responses.calls[0]["input"][1]["content"]
    assert "Who refereed the final?" in user_message
    assert "Szymon Marciniak." in user_message


def test_evaluate_relevance_returns_the_verdict_and_what_it_cost():
    client = FakeClient([(verdict("PARTLY_RELEVANT", "Half an answer."), usage())])
    result = evaluate_relevance("Q?", "A.", client=client)
    assert result.relevance == "PARTLY_RELEVANT"
    assert result.explanation == "Half an answer."
    assert result.cost == calculate_cost("gpt-5.4-mini", usage())


def test_judge_or_none_returns_the_verdict_on_success():
    client = FakeClient([(verdict(), usage())])
    assert judge_or_none("Q?", "A.", client=client).relevance == "RELEVANT"


def test_judge_or_none_never_calls_the_llm_without_an_answer():
    # run_agent_loop returns answer=None when it hits the iteration cap: a system
    # failure, not an irrelevant answer, so it must not reach the relevance chart.
    client = FakeClient([])
    assert judge_or_none("Q?", None, client=client) is None
    assert judge_or_none("Q?", "", client=client) is None
    assert judge_or_none("Q?", "   ", client=client) is None
    assert client.responses.calls == []


def test_judge_or_none_survives_a_broken_judge():
    client = FakeClient([RuntimeError("api down")] * 3)
    assert judge_or_none("Q?", "A.", client=client, sleep=lambda _: None) is None


def test_judge_instructions_describe_this_domain():
    # Guards against reverting to the course's generic RAG-FAQ prompt.
    assert "2022" in JUDGE_INSTRUCTIONS
    assert "World Cup" in JUDGE_INSTRUCTIONS
    for label in ("RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"):
        assert label in JUDGE_INSTRUCTIONS
