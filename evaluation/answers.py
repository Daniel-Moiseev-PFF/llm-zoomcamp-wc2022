"""Run the answer ground truth through each prompt variant, recording what happened.

The same agent, tools and model for every variant — only the developer message
differs, so a difference in the judged score is attributable to the prompt.

Resumable in the same style as the football pipeline: a (variant, id) pair
already in answer-runs.csv is skipped, and a run that fails leaves no row so the
next invocation retries it.

  uv run python -m evaluation.answers [--variant full]
"""

import argparse
import csv
import json
import logging

from agent.loop import run_agent_loop
from evaluation import DATA_DIR, DEFAULT_MODEL
from evaluation.variants import VARIANTS
from monitoring.metrics import classify_tool_path, cost_from_metadata

logger = logging.getLogger(__name__)

QUESTIONS_PATH = DATA_DIR / "answer-ground-truth.csv"
RUNS_PATH = DATA_DIR / "answer-runs.csv"

FIELDNAMES = [
    "variant",
    "id",
    "question",
    "expected_path",
    "actual_path",
    "answer",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost",
    "response_time",
    "iterations",
    "tool_calls",
]


def result_row(variant, question_row, answer, metadata, model) -> dict:
    return {
        "variant": variant,
        "id": question_row["id"],
        "question": question_row["question"],
        "expected_path": question_row["path"],
        "actual_path": classify_tool_path(metadata["tool_calls"]),
        # run_agent_loop returns None at the iteration cap; the judge scores an
        # empty answer as incorrect, which is the honest outcome for that turn.
        "answer": answer or "",
        "prompt_tokens": metadata["prompt_tokens"],
        "completion_tokens": metadata["completion_tokens"],
        "total_tokens": metadata["total_tokens"],
        "cost": cost_from_metadata(model, metadata),
        "response_time": round(metadata["response_time"], 3),
        "iterations": metadata["iterations"],
        "tool_calls": json.dumps([call["name"] for call in metadata["tool_calls"]]),
    }


def run_variant(
    variant,
    questions,
    client,
    model=DEFAULT_MODEL,
    tools=None,
    tool_schemas=None,
    existing=(),
    loop=run_agent_loop,
) -> list[dict]:
    """Run every not-yet-run question under one variant's instructions."""
    instructions = VARIANTS[variant]
    rows = []
    for question_row in questions:
        if (variant, question_row["id"]) in existing:
            continue
        try:
            answer, _messages, metadata = loop(
                client,
                model,
                tools,
                tool_schemas,
                question_row["question"],
                instructions=instructions,
            )
        except Exception:
            logger.warning(
                "%s: question %s failed; leaving it for the next run",
                variant,
                question_row["id"],
                exc_info=True,
            )
            continue
        rows.append(result_row(variant, question_row, answer, metadata, model))
    return rows


def load_questions(path=QUESTIONS_PATH) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_runs(path=RUNS_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def existing_keys(rows) -> set[tuple]:
    return {(row["variant"], row["id"]) for row in rows}


def write_csv(rows, path=RUNS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    from dotenv import load_dotenv
    from openai import OpenAI

    from agent.tools import TOOL_SCHEMAS, execute_sql, read_section, search_prose
    from ingestion.prose import MODEL_PATH
    from ingestion.prose.embedder import Embedder
    from ingestion.prose.store import connect

    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the variants over the questions.")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    questions = load_questions()
    done = load_runs()
    keys = existing_keys(done)
    variants = [args.variant] if args.variant else sorted(VARIANTS)

    client = OpenAI()
    with connect() as conn:
        embedder = Embedder(MODEL_PATH)
        tools = {
            "execute_sql": lambda query: execute_sql(conn, query),
            "search_prose": lambda query, team=None: search_prose(
                conn, embedder, query, team
            ),
            "read_section": lambda article, section: read_section(
                conn, article, section
            ),
        }
        for variant in variants:
            fresh = run_variant(
                variant,
                questions,
                client,
                model=args.model,
                tools=tools,
                tool_schemas=TOOL_SCHEMAS,
                existing=keys,
            )
            print(f"{variant}: {len(fresh)} new runs")
            done += fresh
            write_csv(done)

    print(f"{len(done)} runs -> {RUNS_PATH}")


if __name__ == "__main__":
    main()
