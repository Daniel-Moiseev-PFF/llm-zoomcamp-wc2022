"""Conversation + feedback logging into the `monitoring` Postgres schema.

Reference: llm-zoomcamp 05-monitoring/code/{db_init,db_save,db_feedback}.py —
adapted so every function takes an open psycopg connection instead of opening
its own (the Streamlit app owns a dedicated writable connection), tables are
schema-qualified, and init is idempotent (IF NOT EXISTS, never DROP).

Standalone init: uv run python -m monitoring.db
"""

import json
from datetime import datetime

from monitoring import DB_TIMEZONE


def init_db(conn) -> None:
    """Create the monitoring schema and both tables if absent; commit.

    Statements (all idempotent — this schema holds history, never drop):
      CREATE SCHEMA IF NOT EXISTS monitoring
      CREATE TABLE IF NOT EXISTS monitoring.conversations (
          id SERIAL PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL,
          model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL,
          completion_tokens INTEGER NOT NULL, total_tokens INTEGER NOT NULL,
          response_time FLOAT NOT NULL, cost FLOAT NOT NULL,
          tool_calls JSONB NOT NULL, timestamp TIMESTAMP WITH TIME ZONE NOT NULL)
      CREATE TABLE IF NOT EXISTS monitoring.feedback (
          id SERIAL PRIMARY KEY,
          conversation_id INTEGER REFERENCES monitoring.conversations(id),
          source TEXT NOT NULL, relevance TEXT, explanation TEXT,
          score INTEGER, timestamp TIMESTAMP WITH TIME ZONE NOT NULL)
    """
    conn.execute("CREATE SCHEMA IF NOT EXISTS monitoring")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring.conversations (
            id SERIAL PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL,
            model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL,
            completion_tokens INTEGER NOT NULL, total_tokens INTEGER NOT NULL,
            response_time FLOAT NOT NULL, cost FLOAT NOT NULL,
            tool_calls JSONB NOT NULL, timestamp TIMESTAMP WITH TIME ZONE NOT NULL)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring.feedback (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER REFERENCES monitoring.conversations(id),
            source TEXT NOT NULL, relevance TEXT, explanation TEXT,
            score INTEGER, timestamp TIMESTAMP WITH TIME ZONE NOT NULL)
        """
    )
    conn.commit()


def save_conversation(conn, question, answer, metadata, cost) -> int:
    """INSERT one answered question into monitoring.conversations; return its id.

    `metadata` is run_agent_loop's dict: model_used, prompt_tokens,
    completion_tokens, total_tokens, response_time, tool_calls, iterations.

    Contract (see tests):
    - column/param order: question, answer, model, prompt_tokens,
      completion_tokens, total_tokens, response_time, cost, tool_calls,
      timestamp
    - tool_calls: pass json.dumps(metadata["tool_calls"]) as a string param
      with a `%s::jsonb` cast in the SQL (same trick as `%s::vector` in
      ingestion/prose/store.py)
    - timestamp: datetime.now(DB_TIMEZONE)
    - `RETURNING id`, fetch it, commit, return it (course db_save.py does this)
    """
    SQL = """
        INSERT INTO monitoring.conversations
            (question, answer, model, prompt_tokens, completion_tokens,
             total_tokens, response_time, cost, tool_calls, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            SQL,
            (
                question,
                answer,
                metadata["model_used"],
                metadata["prompt_tokens"],
                metadata["completion_tokens"],
                metadata["total_tokens"],
                metadata["response_time"],
                cost,
                json.dumps(metadata["tool_calls"]),
                datetime.now(DB_TIMEZONE),
            ),
        )
        conversation_id = cur.fetchone()[0]
    conn.commit()
    return conversation_id


def save_feedback(
    conn, conversation_id, source, relevance=None, explanation=None, score=None
) -> None:
    """INSERT one feedback row; commit. Course db_feedback.py, schema-qualified.

    `source` is 'user' (👍/👎 → score=±1) or 'judge' (relevance + explanation,
    added in the monitoring milestone). Param order: conversation_id, source,
    relevance, explanation, score, timestamp (datetime.now(DB_TIMEZONE)).
    """
    SQL = """
        INSERT INTO monitoring.feedback
            (conversation_id, source, relevance, explanation, score, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    conn.execute(
        SQL,
        (
            conversation_id,
            source,
            relevance,
            explanation,
            score,
            datetime.now(DB_TIMEZONE),
        ),
    )
    conn.commit()


def main() -> None:
    from dotenv import load_dotenv

    from ingestion.prose.store import connect

    load_dotenv()
    with connect() as conn:
        init_db(conn)
    print("monitoring schema initialized")


if __name__ == "__main__":
    main()
