"""Write embedded chunks to pgvector (prose.chunks), full refresh each run.

SQL patterns follow llm-zoomcamp 02-vector-search lesson 08 (pgvector): text
vector literal + ::vector cast on insert. Unlike the football pipeline there
is no budgeting or resumability — the corpus is 5 articles and Wikipedia
fetches are free, so drop-and-reload is the simplest correct thing.
"""

import psycopg

from ingestion.football.pipeline import postgres_credentials
from ingestion.prose import EMBEDDING_DIM

CREATE_TABLE_SQL = f"""
    CREATE TABLE prose.chunks (
        id SERIAL PRIMARY KEY,
        article TEXT NOT NULL,
        oldid BIGINT NOT NULL,
        section TEXT NOT NULL,
        chunk_index INT NOT NULL,
        content TEXT NOT NULL,
        teams_mentioned TEXT[] NOT NULL,
        embedding vector({EMBEDDING_DIM}) NOT NULL,
        content_tsv tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english', section), 'A') ||
            setweight(to_tsvector('english', content), 'B')
        ) STORED
    )
"""

# Naming the regconfig is what makes to_tsvector immutable, and immutability is
# what makes it legal in a generated column. Bare to_tsvector(content) depends
# on default_text_search_config and Postgres rejects it here.
CREATE_TSV_INDEX_SQL = """
    CREATE INDEX chunks_content_tsv_idx ON prose.chunks USING GIN (content_tsv)
"""

INSERT_SQL = """
    INSERT INTO prose.chunks
        (article, oldid, section, chunk_index, content, teams_mentioned, embedding)
    VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
"""


def connect():
    return psycopg.connect(postgres_credentials())


def vec_to_str(vector) -> str:
    return "[" + ",".join(str(x) for x in vector) + "]"


def chunk_row(article, chunk, teams, embedding) -> tuple:
    return (
        article.title,
        article.oldid,
        chunk.section,
        chunk.chunk_index,
        chunk.content,
        teams,
        vec_to_str(embedding),
    )


def recreate_table(conn) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("CREATE SCHEMA IF NOT EXISTS prose")
    conn.execute("DROP TABLE IF EXISTS prose.chunks")
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_TSV_INDEX_SQL)


def insert_rows(conn, rows) -> None:
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
