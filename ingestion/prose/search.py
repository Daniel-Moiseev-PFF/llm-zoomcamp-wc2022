"""Cosine search over prose.chunks — lesson 08's pgvector_search, adapted.

Doubles as the manual verification tool and the future agent's vector-search
tool. CLI: uv run python -m ingestion.prose.search "your question" [team]
"""

import sys

from dotenv import load_dotenv

from ingestion.prose import MODEL_PATH
from ingestion.prose.embedder import Embedder
from ingestion.prose.store import connect, vec_to_str


def search(query, embedder, conn, k=5, team=None):
    query_str = vec_to_str(embedder.encode(query))
    sql = """
        SELECT article, section, content, teams_mentioned,
               1 - (embedding <=> %(q)s::vector) AS similarity
        FROM prose.chunks
    """
    params = {"q": query_str, "k": k}
    if team:
        sql += " WHERE %(team)s = ANY(teams_mentioned)"
        params["team"] = team
    sql += " ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s"
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "article": r[0],
            "section": r[1],
            "content": r[2],
            "teams_mentioned": r[3],
            "similarity": r[4],
        }
        for r in rows
    ]


def main() -> None:
    load_dotenv()
    query = sys.argv[1]
    team = sys.argv[2] if len(sys.argv) > 2 else None
    with connect() as conn:
        results = search(query, Embedder(MODEL_PATH), conn, team=team)
    for r in results:
        print(f"[{r['similarity']:.3f}] {r['article']} :: {r['section']}")
        print(r["content"])
        print()


if __name__ == "__main__":
    main()
