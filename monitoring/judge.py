"""LLM-as-judge: score answer relevance on live traffic.

Follows llm-zoomcamp 05-monitoring/code/judge.py (lesson 09). Deviations:
- the instructions are rewritten for this domain — a tool-using World Cup agent
  answering from a match database and Wikipedia prose, not a course FAQ;
- `evaluate_relevance` also reports what the judge call cost, since judging
  every answer roughly doubles the per-question spend;
- `judge_or_none` wraps it so an unavailable judge can never break the chat.

Smoke test (one real API call): uv run python -m monitoring.judge
"""

import logging
import time
from typing import Literal, NamedTuple

from pydantic import BaseModel

from monitoring.llm import llm_structured_retry
from monitoring.metrics import calculate_cost

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "gpt-5.4-mini"


class RelevanceVerdict(BaseModel):
    relevance: Literal["NON_RELEVANT", "PARTLY_RELEVANT", "RELEVANT"]
    explanation: str


class JudgeVerdict(NamedTuple):
    """What gets persisted: the two course fields plus the judge's own cost."""

    relevance: str
    explanation: str
    cost: float


JUDGE_INSTRUCTIONS = """
You are an expert evaluator for a question-answering system about the 2022 FIFA
World Cup. The system routes each question to a relational database of match
data (results, standings, lineups, in-match events) and/or to a vector index
over Wikipedia prose (tournament narrative, controversies, ceremonies), then
answers from whatever those tools returned.

Analyze the relevance of the generated answer to the given question. You see
only the question and the answer — there is no reference answer.

Classify the answer as:
- RELEVANT: the answer addresses the question. Every part of a multi-part
  question is answered, with the specifics the question asked for (score,
  minute, name, referee, round).
- PARTLY_RELEVANT: the answer addresses the question only in part — it covers
  one clause of a multi-part question, or it stays on topic but vague where the
  question asked for a specific fact.
- NON_RELEVANT: the answer does not address the question. This covers saying it
  does not know, declining to answer, an empty answer, and anything about a
  different tournament, match or team than the one asked about.

Declining is the right behaviour when the tools returned nothing, but it is
still NON_RELEVANT: this score measures whether the user got what they asked
for, not whether the system behaved well.

Do not reward length, and do not check the facts against your own World Cup
knowledge — judge relevance only.
""".strip()

JUDGE_PROMPT = """
Question: {question}
Generated Answer: {answer}
""".strip()


def evaluate_relevance(
    question, answer, client=None, model=DEFAULT_JUDGE_MODEL, sleep=time.sleep
) -> JudgeVerdict:
    """Score one answer. Raises if the judge is unreachable — see judge_or_none."""
    if client is None:
        from openai import OpenAI

        client = OpenAI()

    prompt = JUDGE_PROMPT.format(question=question, answer=answer)

    result, usage = llm_structured_retry(
        client,
        JUDGE_INSTRUCTIONS,
        prompt,
        RelevanceVerdict,
        model=model,
        sleep=sleep,
    )

    return JudgeVerdict(
        result.relevance, result.explanation, calculate_cost(model, usage)
    )


def judge_or_none(
    question, answer, client=None, model=DEFAULT_JUDGE_MODEL, sleep=time.sleep
):
    """Score one answer, or return None if it can't be scored. Never raises.

    Returns None without spending a call when there is no answer to score:
    run_agent_loop hands back None at the iteration cap, which is a system
    failure rather than an irrelevant answer, and scoring it would blur the two
    together on the relevance chart. Taking the raw answer (rather than the
    app's fallback string) keeps this module ignorant of how the UI renders it.

    Also returns None if the judge itself keeps failing — the chat has to
    outlive a judge outage.
    """
    if answer is None or not answer.strip():
        return None
    try:
        return evaluate_relevance(
            question, answer, client=client, model=model, sleep=sleep
        )
    except Exception:
        logger.warning(
            "judge failed for question %r; no verdict", question, exc_info=True
        )
        return None


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    result = evaluate_relevance(
        "Who refereed the 2022 World Cup final?",
        "Szymon Marciniak of Poland refereed the final between Argentina and France.",
    )
    print(result.relevance)
    print(result.explanation)
    print(f"judge cost: ${result.cost:.6f}")


if __name__ == "__main__":
    main()
