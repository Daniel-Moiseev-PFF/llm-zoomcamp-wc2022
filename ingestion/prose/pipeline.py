"""Entrypoint: Wikipedia articles -> chunks -> embeddings -> prose.chunks.

Usage: uv run python -m ingestion.prose.pipeline
Full refresh: drops and reloads prose.chunks on every run. Requires the ONNX
model (uv run python scripts/download_model.py, once) and the football.teams
table (structured pipeline) for team tagging.
"""

import logging

from dotenv import load_dotenv

from ingestion.prose import MODEL_PATH
from ingestion.prose.chunk import chunk_article
from ingestion.prose.embedder import Embedder
from ingestion.prose.fetch import fetch_wikitext
from ingestion.prose.manifest import ARTICLES
from ingestion.prose.store import chunk_row, connect, insert_rows, recreate_table
from ingestion.prose.tag import teams_mentioned

logger = logging.getLogger(__name__)


def load_team_names(conn) -> list[str]:
    rows = conn.execute("SELECT team__name FROM football.teams").fetchall()
    return [row[0] for row in rows]


def run(conn, embedder, session=None) -> None:
    team_names = load_team_names(conn)

    def count_tokens(text):
        return len(embedder.tokenizer.encode(text).ids)

    recreate_table(conn)
    total = 0
    for article in ARTICLES:
        wikitext = fetch_wikitext(article.oldid, session=session)
        chunks = chunk_article(wikitext, count_tokens)
        embeddings = embedder.encode_batch([chunk.content for chunk in chunks])
        rows = [
            chunk_row(article, chunk, teams_mentioned(chunk.content, team_names), emb)
            for chunk, emb in zip(chunks, embeddings)
        ]
        insert_rows(conn, rows)
        total += len(rows)
        logger.info("%s: %d chunks", article.title, len(rows))
    logger.info("Loaded %d chunks total", total)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()
    with connect() as conn:
        run(conn, Embedder(MODEL_PATH))


if __name__ == "__main__":
    main()
