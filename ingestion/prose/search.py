"""Three retrieval arms over prose.chunks — vector, lexical, and their fusion.

The vector arm is lesson 08's pgvector_search, adapted. The lexical arm is
Postgres full-text search over the generated `content_tsv` column, and the
hybrid arm fuses the two with Reciprocal Rank Fusion from best-practices
lesson 02.

`search` is what the agent calls; it delegates to whichever arm `DEFAULT_ARM`
names, so the offline evaluation's winner can be adopted in one line. Only the
name `search` is public API — `agent/tools.py` imports it.

CLI: uv run python -m ingestion.prose.search "your question" [team]
"""

import sys

from dotenv import load_dotenv

from ingestion.prose import MODEL_PATH
from ingestion.prose.embedder import Embedder
from ingestion.prose.store import connect, vec_to_str

# Every arm returns rows in this order; the first three are the natural key.
COLUMNS = ("article", "section", "chunk_index", "content", "teams_mentioned")


def natural_key(result) -> tuple:
    """Identify a chunk by (article, section, chunk_index).

    Deliberately not `chunks.id`: that is a SERIAL, and the prose pipeline
    drops and recreates the table on every run, so ids are reassigned. A
    committed ground-truth file keyed on them would silently start scoring
    against different chunks after a re-ingest.
    """
    return (result["article"], result["section"], result["chunk_index"])


def as_dicts(rows, score_field: str) -> list[dict]:
    return [dict(zip(COLUMNS, row)) | {score_field: row[-1]} for row in rows]


def search_vector(query, embedder, conn, k=5, team=None) -> list[dict]:
    """Cosine nearest neighbours over the chunk embeddings."""
    sql = """
        SELECT article, section, chunk_index, content, teams_mentioned,
               1 - (embedding <=> %(q)s::vector) AS similarity
        FROM prose.chunks
    """
    params = {"q": vec_to_str(embedder.encode(query)), "k": k}
    if team:
        sql += " WHERE %(team)s = ANY(teams_mentioned)"
        params["team"] = team
    sql += " ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s"
    return as_dicts(conn.execute(sql, params).fetchall(), "similarity")


def search_lexical(query, conn, k=5, team=None) -> list[dict]:
    """Postgres full-text search — the keyword baseline the vector arm has to beat.

    Needs no embedder, which is most of the point: it is the cheap arm.
    """
    sql = """
        SELECT article, section, chunk_index, content, teams_mentioned,
               ts_rank_cd(content_tsv, plainto_tsquery('english', %(q)s)) AS rank
        FROM prose.chunks
        WHERE content_tsv @@ plainto_tsquery('english', %(q)s)
    """
    params = {"q": query, "k": k}
    if team:
        sql += " AND %(team)s = ANY(teams_mentioned)"
        params["team"] = team
    sql += " ORDER BY rank DESC LIMIT %(k)s"
    return as_dicts(conn.execute(sql, params).fetchall(), "rank")


def rrf(result_lists, k=1, num_results=10) -> list[dict]:
    """Reciprocal Rank Fusion — best-practices lesson 02, keyed on the natural key.

    Each document scores 1/(k + rank + 1) in every list it appears in, summed.
    Larger k flattens the difference between rank positions. Documents found by
    both arms rise above those found by only one, which is the whole idea.
    """
    scores: dict[tuple, float] = {}
    documents: dict[tuple, dict] = {}
    for results in result_lists:
        for rank, result in enumerate(results):
            key = natural_key(result)
            if key not in scores:
                scores[key] = 0.0
                documents[key] = result
            scores[key] += 1 / (k + rank + 1)
    # sorted is stable, so documents tied on score keep their first-seen order.
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [documents[key] | {"rrf_score": score} for key, score in ranked[:num_results]]


def search_hybrid(query, embedder, conn, k=5, team=None, candidates=None, rrf_k=1):
    """Both arms, fused. `candidates` is how deep each arm is read before fusing."""
    depth = candidates or k
    lists = [
        search_vector(query, embedder, conn, k=depth, team=team),
        search_lexical(query, conn, k=depth, team=team),
    ]
    return rrf(lists, k=rrf_k, num_results=k)


DEFAULT_ARM = search_vector


def search(query, embedder, conn, k=5, team=None) -> list[dict]:
    """The arm the agent searches with. Set DEFAULT_ARM to change it everywhere."""
    return DEFAULT_ARM(query, embedder, conn, k=k, team=team)


def main() -> None:
    load_dotenv()
    query = sys.argv[1]
    team = sys.argv[2] if len(sys.argv) > 2 else None
    with connect() as conn:
        results = search(query, Embedder(MODEL_PATH), conn, team=team)
    for r in results:
        score = r.get("similarity", r.get("rank", r.get("rrf_score")))
        print(f"[{score:.3f}] {r['article']} :: {r['section']}")
        print(r["content"])
        print()


if __name__ == "__main__":
    main()
