from app.helpers import answer_or_fallback, format_caption, thumbs_to_score

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
