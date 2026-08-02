"""Generate retrieval ground truth: questions whose answer is a known chunk.

Follows llm-zoomcamp 04-evaluation/lessons/02-ground-truth.md — ask an LLM for
questions a given record would answer, then that record is by construction the
gold document for them. Deviations:

- rows are keyed on (article, section, chunk_index), never on prose.chunks.id,
  because the prose pipeline drops and recreates the table on every run and the
  SERIAL is reassigned;
- one bad chunk is logged and skipped rather than aborting the run.

  uv run python -m evaluation.ground_truth [--limit N] [--per-chunk N]
"""

import argparse
import csv
import logging
import time

from pydantic import BaseModel

from evaluation import DATA_DIR, DEFAULT_MODEL
from monitoring.llm import llm_structured_retry

logger = logging.getLogger(__name__)

GROUND_TRUTH_PATH = DATA_DIR / "retrieval-ground-truth.csv"
FIELDNAMES = ["article", "section", "chunk_index", "question"]

# Below this, a chunk is a stub heading or a one-line caption: there is nothing
# in it specific enough to write a question that only it can answer.
MIN_CONTENT_CHARS = 200

DEFAULT_PER_CHUNK = 3


class GeneratedQuestions(BaseModel):
    questions: list[str]


GROUND_TRUTH_INSTRUCTIONS = """
You emulate someone reading about the 2022 FIFA World Cup in Qatar and asking a
question that this passage answers.

Formulate {per_chunk} questions this reader might ask, based on the passage
below. The passage must contain the answer. Questions should be complete
sentences, specific enough that this passage is the one that answers them —
name the team, match, player or event involved rather than saying "the team" or
"this match".

If possible, use as few words as possible from the passage. Rephrase rather
than quote.

The output should resemble how people ask questions on the internet. Not too
formal, not too short, not too long.
""".strip()

CHUNK_PROMPT = """
Article: {article}
Section: {section}

{content}
""".strip()


def generate_for_chunk(
    chunk, client, model=DEFAULT_MODEL, per_chunk=DEFAULT_PER_CHUNK, sleep=time.sleep
) -> list[dict]:
    """Ask for `per_chunk` questions about one chunk. Raises if the call fails."""
    prompt = CHUNK_PROMPT.format(
        article=chunk["article"], section=chunk["section"], content=chunk["content"]
    )
    result, _usage = llm_structured_retry(
        client,
        GROUND_TRUTH_INSTRUCTIONS.format(per_chunk=per_chunk),
        prompt,
        GeneratedQuestions,
        model=model,
        sleep=sleep,
    )
    return [
        {
            "article": chunk["article"],
            "section": chunk["section"],
            "chunk_index": chunk["chunk_index"],
            "question": question,
        }
        for question in result.questions
    ]


def rows_for_chunks(
    chunks, client, model=DEFAULT_MODEL, per_chunk=DEFAULT_PER_CHUNK, sleep=time.sleep
) -> list[dict]:
    """Every chunk's questions, skipping the ones too short or too broken."""
    rows = []
    for chunk in chunks:
        if len(chunk["content"]) < MIN_CONTENT_CHARS:
            logger.info("skipping short chunk %s :: %s", chunk["article"], chunk["section"])
            continue
        try:
            rows.extend(generate_for_chunk(chunk, client, model, per_chunk, sleep))
        except Exception:
            logger.warning(
                "question generation failed for %s :: %s [%s]",
                chunk["article"],
                chunk["section"],
                chunk["chunk_index"],
                exc_info=True,
            )
    return rows


def load_chunks(conn, limit=None) -> list[dict]:
    sql = """
        SELECT article, section, chunk_index, content
        FROM prose.chunks
        ORDER BY article, section, chunk_index
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    return [
        {"article": r[0], "section": r[1], "chunk_index": r[2], "content": r[3]}
        for r in rows
    ]


def write_csv(rows, path=GROUND_TRUTH_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    from dotenv import load_dotenv
    from openai import OpenAI

    from ingestion.prose.store import connect

    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate retrieval ground truth.")
    parser.add_argument("--limit", type=int, default=None, help="chunks to use")
    parser.add_argument(
        "--per-chunk", type=int, default=DEFAULT_PER_CHUNK, help="questions per chunk"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    with connect() as conn:
        chunks = load_chunks(conn, limit=args.limit)
    print(f"{len(chunks)} chunks")

    rows = rows_for_chunks(chunks, OpenAI(), args.model, args.per_chunk)
    write_csv(rows)
    print(f"{len(rows)} questions -> {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
