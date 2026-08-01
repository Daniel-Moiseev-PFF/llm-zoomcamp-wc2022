"""Agent tools: raw read-only SQL, prose vector search, section expansion.

Tool-schema style and the make_call dispatcher follow llm-zoomcamp
01-agentic-rag lessons 13-14, extended to a name->function registry.
"""

import json

from ingestion.prose.search import search as prose_search

MAX_ROWS = 50


def execute_sql(conn, query: str) -> dict:
    """Run a read-only query; DB errors come back as output, not exceptions,
    so the agent can see what went wrong and fix its SQL."""
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchmany(MAX_ROWS + 1)
            columns = [col.name for col in cur.description]
    except Exception as exc:  # noqa: BLE001 - error text is the tool output
        conn.rollback()
        return {"error": str(exc)}
    result = {
        "columns": columns,
        "rows": [list(row) for row in rows[:MAX_ROWS]],
        "row_count": min(len(rows), MAX_ROWS),
    }
    if len(rows) > MAX_ROWS:
        result["truncated"] = True
    return result


def search_prose(conn, embedder, query: str, team: str | None = None) -> list[dict]:
    results = prose_search(query, embedder, conn, team=team)
    for r in results:
        r["similarity"] = round(float(r["similarity"]), 3)
    return results


def read_section(conn, article: str, section: str) -> str:
    rows = conn.execute(
        """
        SELECT content FROM prose.chunks
        WHERE article = %s AND section = %s
        ORDER BY chunk_index
        """,
        (article, section),
    ).fetchall()
    return "\n\n".join(row[0] for row in rows)


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "execute_sql",
        "description": (
            "Run a read-only SQL query against the World Cup 2022 relational "
            "database (Postgres). Use for facts and stats: results, standings, "
            "lineups, who played whom. The schema is described in your "
            "instructions. Errors are returned as output — fix the query and retry."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The SQL query to run."}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_prose",
        "description": (
            "Semantic search over Wikipedia prose about the 2022 World Cup "
            "(tournament narrative, controversies, ceremonies, match stories). "
            "Use for narrative or opinion-shaped questions. Returns the most "
            "similar chunks with their article and section."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "team": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional team-name filter (API-Football name, e.g. "
                        "'USA', 'South Korea'). Only chunks mentioning the team."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_section",
        "description": (
            "Read the full text of one article section, e.g. after search_prose "
            "returned a promising chunk and you need the surrounding context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "article": {"type": "string", "description": "Exact article title."},
                "section": {"type": "string", "description": "Exact section heading."},
            },
            "required": ["article", "section"],
            "additionalProperties": False,
        },
    },
]


def make_call(call, tools: dict) -> dict:
    args = json.loads(call.arguments)
    result = tools[call.name](**args)
    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": json.dumps(result, indent=2, default=str),
    }
