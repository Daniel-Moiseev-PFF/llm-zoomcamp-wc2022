from types import SimpleNamespace

from app.helpers import (
    answer_or_fallback,
    format_caption,
    format_verdict,
    thumbs_to_score,
)

METADATA = {
    "model_used": "gpt-5.4-mini",
    "response_time": 2.13,
    "prompt_tokens": 1000,
    "completion_tokens": 234,
    "total_tokens": 1234,
    "tool_calls": [
        {"name": "execute_sql", "arguments": {"query": "SELECT 1"}},
        {"name": "search_prose", "arguments": {"query": "final"}},
    ],
    "iterations": 3,
}


def test_format_caption_includes_all_fields():
    caption = format_caption(METADATA, 0.0012)
    assert "gpt-5.4-mini" in caption
    assert "3 calls" in caption
    assert "execute_sql, search_prose" in caption
    assert "1234 tokens" in caption
    assert "2.1s" in caption
    assert "$0.0012" in caption


def test_format_caption_without_tool_calls_says_none():
    metadata = {**METADATA, "tool_calls": []}
    assert "tools: none" in format_caption(metadata, 0.0)


def test_thumbs_to_score():
    # st.feedback("thumbs") yields 0 for thumbs-down, 1 for thumbs-up.
    assert thumbs_to_score(0) == -1
    assert thumbs_to_score(1) == 1


def test_answer_or_fallback():
    assert answer_or_fallback("An answer.") == "An answer."
    assert answer_or_fallback(None) == "(no answer — iteration cap reached)"


def verdict(relevance, explanation="Because."):
    return SimpleNamespace(relevance=relevance, explanation=explanation, cost=0.0001)


def test_format_verdict_colours_each_relevance():
    assert ":green-badge[judge: RELEVANT]" in format_verdict(verdict("RELEVANT"))
    assert ":orange-badge[judge: PARTLY_RELEVANT]" in format_verdict(
        verdict("PARTLY_RELEVANT")
    )
    assert ":red-badge[judge: NON_RELEVANT]" in format_verdict(
        verdict("NON_RELEVANT")
    )


def test_format_verdict_includes_the_explanation():
    assert "Because." in format_verdict(verdict("RELEVANT"))


def test_format_verdict_is_empty_when_the_judge_did_not_run():
    assert format_verdict(None) == ""


def test_format_verdict_falls_back_to_grey_for_an_unknown_label():
    assert ":grey-badge[judge: WEIRD]" in format_verdict(verdict("WEIRD"))
