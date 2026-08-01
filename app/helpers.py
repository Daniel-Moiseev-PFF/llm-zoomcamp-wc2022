"""Pure helpers for the Streamlit app — no streamlit import, unit-testable."""


def format_caption(metadata: dict, cost: float) -> str:
    """One-line footer under each answer, mirroring agent/cli.py's print_result."""
    tool_trace = ", ".join(c["name"] for c in metadata["tool_calls"]) or "none"
    return (
        f"{metadata['model_used']} | {metadata['iterations']} calls | "
        f"tools: {tool_trace} | {metadata['total_tokens']} tokens | "
        f"{metadata['response_time']:.1f}s | ${cost:.4f}"
    )


def thumbs_to_score(value: int) -> int:
    """Map st.feedback("thumbs") values (0=down, 1=up) to feedback scores ±1."""
    return 1 if value == 1 else -1


def answer_or_fallback(answer) -> str:
    """The conversations.answer column is NOT NULL; cover the iteration-cap case."""
    return answer if answer is not None else "(no answer — iteration cap reached)"
