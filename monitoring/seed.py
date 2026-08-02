"""Fabricate back-dated traffic so the Grafana dashboard has something to show.

Follows llm-zoomcamp 05-monitoring/code/generate_data.py (sample pools, the
feedback probabilities, the skew towards happy users) with the back-dating loop
from cohorts/2024/04-monitoring/app/generate_data.py, so a fresh dashboard opens
on a full time axis instead of three lonely points.

Nothing here calls an LLM: every verdict, token count and latency is invented.
Seeded questions carry SEED_MARKER so fabricated rows are obvious in the
dashboard's table panel and can be removed again with --purge.

    uv run python -m monitoring.seed --hours 6 --count 150 --seed 42
    uv run python -m monitoring.seed --purge
"""

import argparse
import random
from datetime import datetime, timedelta
from types import SimpleNamespace

from monitoring import DB_TIMEZONE
from monitoring.db import init_db, save_conversation, save_feedback
from monitoring.metrics import calculate_cost, cost_from_metadata

SEED_MARKER = "[seed]"

MODEL = "gpt-5.4-mini"

# Question/answer pools per routing path. The mixed ones are the verified
# two-tool questions from docs/mixed-routing-questions.md.
SEED_TRAFFIC = {
    "mixed": [
        (
            "What was the score when Argentina lost in the group stage, and how "
            "big an upset was that considered?",
            "Saudi Arabia beat Argentina 2-1 in Group C on 22 November 2022. It "
            "was widely described at the time as one of the biggest upsets in "
            "World Cup history.",
        ),
        (
            "In what minutes did Japan score against Spain, and what was "
            "controversial about the winning goal?",
            "Doan scored in the 48th minute and Tanaka in the 51st. The winner "
            "survived a VAR check on whether the ball had wholly crossed the "
            "byline before Mitoma cut it back.",
        ),
        (
            "Who refereed the final, and were there any officiating "
            "controversies at the tournament?",
            "Szymon Marciniak of Poland refereed the final. The tournament drew "
            "attention for semi-automated offside technology and for unusually "
            "long stoppage-time additions.",
        ),
        (
            "Which teams played the opening match and what was the score, and "
            "what happened at the opening ceremony?",
            "Ecuador beat the hosts Qatar 2-0. The ceremony at Al Bayt Stadium "
            "featured Morgan Freeman and Ghanim Al-Muftah.",
        ),
        (
            "Who finished top of Iran's group, and what protests surrounded the "
            "Iranian team?",
            "England topped Group B. Iran's players stayed silent through their "
            "anthem before the England match, in support of protests at home.",
        ),
    ],
    "sql": [
        (
            "How many goals did Mbappe score in the final?",
            "Three: a penalty in the 80th minute, an open-play goal in the 81st, "
            "and another penalty in the 118th.",
        ),
        (
            "Which teams reached the quarter-finals?",
            "Croatia, Brazil, Netherlands, Argentina, Morocco, Portugal, England "
            "and France.",
        ),
        (
            "What was the score in the third-place match?",
            "Croatia beat Morocco 2-1.",
        ),
        (
            "Did Messi and Mbappe play against each other?",
            "Yes — both started the final on 18 December 2022.",
        ),
        (
            "How many matches did Morocco win in normal time?",
            "Three: Belgium, Canada and Portugal.",
        ),
    ],
    "prose": [
        (
            "What was the biggest scandal involving Switzerland?",
            "The Serbia match, where Xhaka and Shaqiri were at the centre of "
            "nationalist gestures and a heated post-match confrontation.",
        ),
        (
            "How was Morocco's run to the semi-finals received?",
            "As the story of the tournament — the first African and first Arab "
            "team to reach a World Cup semi-final, with huge support in Qatar.",
        ),
        (
            "What controversies surrounded the choice of Qatar as host?",
            "Treatment of migrant workers, LGBT rights, the moving of the "
            "tournament to winter, and long-standing bidding allegations.",
        ),
        (
            "What happened with the OneLove armbands?",
            "Several European captains dropped plans to wear them after FIFA "
            "threatened sporting sanctions.",
        ),
    ],
    "none": [
        (
            "Who won Euro 2024?",
            "I can only answer questions about the 2022 World Cup in Qatar.",
        ),
        (
            "What's the weather like today?",
            "I can only answer questions about the 2022 World Cup in Qatar.",
        ),
    ],
}

PATH_WEIGHTS = {"sql": 0.35, "mixed": 0.30, "prose": 0.25, "none": 0.10}

# Latency tracks tool count — the agent loops more on mixed questions.
LATENCY_RANGE = {
    "none": (1.0, 3.0),
    "sql": (3.0, 9.0),
    "prose": (4.0, 10.0),
    "mixed": (6.0, 18.0),
}

# A no-tool answer is a refusal, so the judge marks it down.
RELEVANCE_WEIGHTS = {
    "sql": {"RELEVANT": 0.78, "PARTLY_RELEVANT": 0.17, "NON_RELEVANT": 0.05},
    "prose": {"RELEVANT": 0.62, "PARTLY_RELEVANT": 0.30, "NON_RELEVANT": 0.08},
    "mixed": {"RELEVANT": 0.55, "PARTLY_RELEVANT": 0.35, "NON_RELEVANT": 0.10},
    "none": {"RELEVANT": 0.05, "PARTLY_RELEVANT": 0.15, "NON_RELEVANT": 0.80},
}

# Users mostly agree with the judge, so the two charts rhyme without matching.
THUMBS_UP_PROBABILITY = {
    "RELEVANT": 0.90,
    "PARTLY_RELEVANT": 0.60,
    "NON_RELEVANT": 0.20,
}

JUDGE_PROBABILITY = 0.95  # the app judges every answer; leave room for outages
USER_PROBABILITY = 0.45  # people don't always click

SEED_QUERIES = [
    "SELECT * FROM football.fixtures WHERE fixture__id = 1",
    "SELECT team__name, points FROM football.standings ORDER BY points DESC",
    "SELECT player__name, time__elapsed FROM football.events WHERE type = 'Goal'",
]
SEED_SEARCHES = ["opening ceremony", "controversies", "the final", "group stage upset"]
SEED_SECTIONS = [
    ("2022 FIFA World Cup", "Officiating"),
    ("List of 2022 FIFA World Cup controversies", "Match incidents"),
    ("2022 FIFA World Cup final", "Post-match"),
]


def weighted_choice(weights: dict, rng):
    """One key, chosen in proportion to its weight (rng.choices, keys ordered)."""
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def fake_tool_calls(path, rng):
    """Tool calls in run_agent_loop's shape: [{"name", "arguments"}] in call order."""
    if path == "none":
        return []

    def sql_call():
        return {"name": "execute_sql", "arguments": {"query": rng.choice(SEED_QUERIES)}}

    def prose_call():
        return {
            "name": "search_prose",
            "arguments": {"query": rng.choice(SEED_SEARCHES), "team": None},
        }

    def section_call():
        article, section = rng.choice(SEED_SECTIONS)
        return {
            "name": "read_section",
            "arguments": {"article": article, "section": section},
        }

    if path == "sql":
        # Roughly one SQL turn in four needs a second go at the query.
        return [sql_call(), sql_call()] if rng.random() < 0.25 else [sql_call()]
    if path == "prose":
        calls = [prose_call()]
        if rng.random() < 0.4:
            calls.append(section_call())
        return calls
    calls = [sql_call(), prose_call()]
    if rng.random() < 0.3:
        calls.append(section_call())
    return calls


def fake_metadata(path, tool_calls, rng):
    """run_agent_loop's metadata dict, with token counts for a tool-using agent.

    Prompt tokens dominate and grow with tool count: the instructions are long
    and every tool result is echoed back into the next request.
    """
    prompt_tokens = rng.randint(1800, 4000) + 1400 * len(tool_calls)
    completion_tokens = rng.randint(120, 600)
    low, high = LATENCY_RANGE[path]
    return {
        "model_used": MODEL,
        "response_time": rng.uniform(low, high),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "tool_calls": tool_calls,
        "iterations": len(tool_calls) + 1,
    }


def seed_timestamps(end, hours, count, rng):
    """`count` ascending tz-aware timestamps spread across [end - hours, end].

    The course strides forward by a random gap until it passes the end, which
    honours the window but not the count; drawing offsets and sorting them
    honours both and is irregular enough to look like real traffic.
    """
    window = timedelta(hours=hours)
    offsets = sorted(rng.uniform(0, window.total_seconds()) for _ in range(count))
    return [end - window + timedelta(seconds=offset) for offset in offsets]


def feedback_time(timestamp, end, rng):
    """Feedback lands shortly after its answer, never past the window's end."""
    return min(timestamp + timedelta(seconds=rng.uniform(1, 120)), end)


def generate_one(conn, timestamp, end, rng) -> int:
    """Fabricate one conversation plus its feedback; return the conversation id."""
    path = weighted_choice(PATH_WEIGHTS, rng)
    question, answer = rng.choice(SEED_TRAFFIC[path])
    tool_calls = fake_tool_calls(path, rng)
    metadata = fake_metadata(path, tool_calls, rng)
    # Derived, not random, so the cost and token panels tell the same story.
    cost = cost_from_metadata(metadata["model_used"], metadata)

    conversation_id = save_conversation(
        conn,
        f"{SEED_MARKER} {question}",
        answer,
        metadata,
        cost,
        timestamp=timestamp,
    )

    relevance = None
    if rng.random() < JUDGE_PROBABILITY:
        relevance = weighted_choice(RELEVANCE_WEIGHTS[path], rng)
        judge_usage = SimpleNamespace(
            input_tokens=rng.randint(200, 500), output_tokens=rng.randint(40, 120)
        )
        save_feedback(
            conn,
            conversation_id,
            "judge",
            relevance=relevance,
            explanation=f"Answer is {relevance.lower().replace('_', ' ')}.",
            cost=calculate_cost(MODEL, judge_usage),
            timestamp=feedback_time(timestamp, end, rng),
        )
    if rng.random() < USER_PROBABILITY:
        thumbs_up = rng.random() < THUMBS_UP_PROBABILITY.get(relevance, 0.7)
        save_feedback(
            conn,
            conversation_id,
            "user",
            score=1 if thumbs_up else -1,
            timestamp=feedback_time(timestamp, end, rng),
        )
    return conversation_id


# Scoped to the marker and only reachable via --purge. init_db's "never drop"
# rule is about protecting real history; these rows were never real.
PURGE_FEEDBACK_SQL = """
    DELETE FROM monitoring.feedback
    WHERE conversation_id IN (
        SELECT id FROM monitoring.conversations WHERE question LIKE %s
    )
"""
PURGE_CONVERSATIONS_SQL = """
    DELETE FROM monitoring.conversations WHERE question LIKE %s
"""


def purge(conn) -> int:
    """Delete previously seeded rows; return how many conversations went."""
    like = (f"{SEED_MARKER}%",)
    with conn.cursor() as cur:
        cur.execute(PURGE_FEEDBACK_SQL, like)  # FK child first
        cur.execute(PURGE_CONVERSATIONS_SQL, like)
        deleted = cur.rowcount
    conn.commit()
    return deleted


def main() -> None:
    from dotenv import load_dotenv

    from ingestion.prose.store import connect

    parser = argparse.ArgumentParser(description="Seed fabricated monitoring traffic.")
    parser.add_argument("--hours", type=float, default=6.0, help="window to fill")
    parser.add_argument("--count", type=int, default=150, help="conversations to make")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument(
        "--purge", action="store_true", help="delete seeded rows, then exit"
    )
    args = parser.parse_args()

    load_dotenv()
    rng = random.Random(args.seed)
    with connect() as conn:
        init_db(conn)
        if args.purge:
            print(f"purged {purge(conn)} seeded conversations")
            return
        end = datetime.now(DB_TIMEZONE)
        for timestamp in seed_timestamps(end, args.hours, args.count, rng):
            generate_one(conn, timestamp, end, rng)
    print(f"seeded {args.count} conversations over the last {args.hours}h")


if __name__ == "__main__":
    main()
