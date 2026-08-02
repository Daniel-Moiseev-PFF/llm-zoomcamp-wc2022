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
      ALTER TABLE monitoring.feedback ADD COLUMN IF NOT EXISTS cost FLOAT
      CREATE INDEX IF NOT EXISTS conversations_timestamp_idx ...
      CREATE INDEX IF NOT EXISTS feedback_conversation_id_idx ...
      CREATE INDEX IF NOT EXISTS feedback_timestamp_idx ...
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
    # Added after the table shipped, so it has to be a separate ALTER: the
    # judge is a second LLM call per question and pays its own way.
    conn.execute("ALTER TABLE monitoring.feedback ADD COLUMN IF NOT EXISTS cost FLOAT")
    # Every dashboard panel filters on timestamp and joins feedback by conversation.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS conversations_timestamp_idx "
        "ON monitoring.conversations (timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS feedback_conversation_id_idx "
        "ON monitoring.feedback (conversation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS feedback_timestamp_idx "
        "ON monitoring.feedback (timestamp)"
    )
    conn.commit()


def save_conversation(conn, question, answer, metadata, cost, timestamp=None) -> int:
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
    - timestamp: defaults to datetime.now(DB_TIMEZONE); monitoring.seed passes
      one explicitly to back-date fabricated traffic
    - `RETURNING id`, fetch it, commit, return it (course db_save.py does this)
    """
    SQL = """
        INSERT INTO monitoring.conversations
            (question, answer, model, prompt_tokens, completion_tokens,
             total_tokens, response_time, cost, tool_calls, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id
    """
    if timestamp is None:
        timestamp = datetime.now(DB_TIMEZONE)
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
                timestamp,
            ),
        )
        conversation_id = cur.fetchone()[0]
    conn.commit()
    return conversation_id


def save_feedback(
    conn,
    conversation_id,
    source,
    relevance=None,
    explanation=None,
    score=None,
    cost=None,
    timestamp=None,
) -> None:
    """INSERT one feedback row; commit. Course db_feedback.py, schema-qualified.

    `source` is 'user' (👍/👎 → score=±1) or 'judge' (relevance + explanation +
    what the judge call cost). Param order: conversation_id, source, relevance,
    explanation, score, timestamp, cost — `cost` trails the original six
    because it was added to the table after it shipped.

    `timestamp` defaults to now; monitoring.seed passes one to back-date rows.
    """
    SQL = """
        INSERT INTO monitoring.feedback
            (conversation_id, source, relevance, explanation, score, timestamp, cost)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    if timestamp is None:
        timestamp = datetime.now(DB_TIMEZONE)
    conn.execute(
        SQL,
        (conversation_id, source, relevance, explanation, score, timestamp, cost),
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
