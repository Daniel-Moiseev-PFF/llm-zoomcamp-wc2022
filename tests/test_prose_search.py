"""The three retrieval arms, tested without a database or an embedding model.

The fake connection records every (sql, params) pair it is handed, so an arm is
checked by what it asks Postgres for rather than by what comes back.
"""

from ingestion.prose.search import (
    DEFAULT_ARM,
    natural_key,
    rrf,
    search,
    search_hybrid,
    search_lexical,
    search_vector,
)

# (article, section, chunk_index, content, teams_mentioned, score)
ROW = (
    "2022 FIFA World Cup final",
    "Summary",
    0,
    "Argentina won on penalties.",
    ["Argentina", "France"],
    0.87,
)

QUERY = "who won the final"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConnection:
    """Records every query; hands back one scripted batch of rows per execute."""

    def __init__(self, *row_batches):
        self.calls = []
        self._batches = list(row_batches)

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        rows = self._batches.pop(0) if self._batches else []
        return FakeResult(rows)


class FakeEmbedder:
    def __init__(self):
        self.encoded = []

    def encode(self, text):
        self.encoded.append(text)
        return [0.1, 0.2, 0.3]


def doc(name, chunk_index=0):
    return {
        "article": name,
        "section": "s",
        "chunk_index": chunk_index,
        "content": f"{name} content",
        "teams_mentioned": [],
    }


def articles(results):
    return [r["article"] for r in results]


def run_every_arm(conn_factory, team=None):
    """Run all three arms, returning {arm name: [(sql, params), ...]}."""
    vector_conn = conn_factory()
    search_vector(QUERY, FakeEmbedder(), vector_conn, team=team)
    lexical_conn = conn_factory()
    search_lexical(QUERY, lexical_conn, team=team)
    hybrid_conn = conn_factory()
    search_hybrid(QUERY, FakeEmbedder(), hybrid_conn, team=team)
    return {
        "vector": vector_conn.calls,
        "lexical": lexical_conn.calls,
        "hybrid": hybrid_conn.calls,
    }


def test_rrf_reproduces_the_lesson_worked_example():
    # llm-zoomcamp 06-best-practices/lessons/02-hybrid-search.md, k=1:
    # text [A B C D E] + vector [C B F G A] fuses to C, A/B, F, D/G, E.
    # C wins on being high in both lists; ties keep their first-seen order.
    text = [doc(n) for n in "ABCDE"]
    vector = [doc(n) for n in "CBFGA"]
    assert articles(rrf([text, vector], k=1, num_results=10)) == list("CABFDGE")


def test_rrf_truncates_to_num_results():
    text = [doc(n) for n in "ABCDE"]
    assert articles(rrf([text], num_results=2)) == ["A", "B"]


def test_rrf_fuses_on_the_whole_natural_key_not_just_the_article():
    # Two chunks of the same section are different documents. Keying on the
    # article alone would collapse them and inflate the winner's score.
    same_article = [doc("A", chunk_index=0), doc("A", chunk_index=1)]
    assert len(rrf([same_article])) == 2


def test_rrf_reports_the_fused_score():
    # Hybrid results carry neither arm's native score, so without this the
    # caller cannot tell how a document earned its position.
    fused = rrf([[doc("A")], [doc("A")]], k=1)
    assert fused[0]["rrf_score"] == 1.0  # 1/(1+0+1) from each of the two lists


def test_natural_key_is_the_reingest_stable_triple():
    # Not chunks.id: that is a SERIAL and gets reassigned on every re-ingest,
    # which would silently repoint the committed ground truth at other chunks.
    assert natural_key(doc("A", chunk_index=3)) == ("A", "s", 3)


def test_vector_arm_returns_the_row_as_a_dict():
    conn = FakeConnection([ROW])
    results = search_vector(QUERY, FakeEmbedder(), conn)
    assert results == [
        {
            "article": "2022 FIFA World Cup final",
            "section": "Summary",
            "chunk_index": 0,
            "content": "Argentina won on penalties.",
            "teams_mentioned": ["Argentina", "France"],
            "similarity": 0.87,
        }
    ]


def test_lexical_arm_returns_the_vector_shape_with_a_rank():
    conn = FakeConnection([ROW])
    results = search_lexical(QUERY, conn)
    assert results[0]["rank"] == 0.87
    assert "similarity" not in results[0]
    assert results[0]["chunk_index"] == 0


def test_lexical_arm_ranks_with_full_text_search():
    conn = FakeConnection([ROW])
    search_lexical(QUERY, conn)
    sql, params = conn.calls[0]
    assert "content_tsv @@ plainto_tsquery('english', %(q)s)" in sql
    assert "ts_rank_cd" in sql
    assert params["q"] == QUERY


def test_every_arm_parameterises_the_user_query():
    # The query text must never reach the SQL string itself.
    for arm, calls in run_every_arm(lambda: FakeConnection([ROW], [ROW])).items():
        for sql, params in calls:
            assert QUERY not in sql, arm
            assert params, arm


def test_every_arm_is_read_only():
    for arm, calls in run_every_arm(lambda: FakeConnection([ROW], [ROW])).items():
        for sql, _ in calls:
            upper = sql.upper()
            for statement in ("INSERT", "UPDATE ", "DELETE", "DROP", "ALTER"):
                assert statement not in upper, f"{arm}: {statement}"


def test_team_filter_reaches_the_params_in_every_arm():
    arms = run_every_arm(lambda: FakeConnection([ROW], [ROW]), team="Switzerland")
    for arm, calls in arms.items():
        for sql, params in calls:
            assert params["team"] == "Switzerland", arm
            assert "ANY(teams_mentioned)" in sql, arm


def test_search_delegates_to_the_default_arm():
    delegated, direct = FakeConnection([ROW]), FakeConnection([ROW])
    assert search(QUERY, FakeEmbedder(), delegated) == DEFAULT_ARM(
        QUERY, FakeEmbedder(), direct
    )
    assert delegated.calls[0][0] == direct.calls[0][0]


def test_hybrid_asks_each_arm_for_the_candidate_depth_not_the_final_k():
    # Fusing two top-5 lists can only ever see 10 documents; the pool has to be
    # deeper than the cut for RRF to have anything to reorder.
    conn = FakeConnection([ROW], [ROW])
    search_hybrid(QUERY, FakeEmbedder(), conn, k=5, candidates=20)
    assert [params["k"] for _, params in conn.calls] == [20, 20]


def test_hybrid_defaults_the_candidate_depth_to_k():
    conn = FakeConnection([ROW], [ROW])
    search_hybrid(QUERY, FakeEmbedder(), conn, k=3)
    assert [params["k"] for _, params in conn.calls] == [3, 3]


def test_hybrid_returns_at_most_k_fused_results():
    rows = [
        ("A", "s", 0, "a", [], 0.9),
        ("B", "s", 0, "b", [], 0.8),
        ("C", "s", 0, "c", [], 0.7),
    ]
    conn = FakeConnection(rows, rows)
    assert len(search_hybrid(QUERY, FakeEmbedder(), conn, k=2, candidates=3)) == 2


def test_hybrid_embeds_the_query_once():
    embedder = FakeEmbedder()
    search_hybrid(QUERY, embedder, FakeConnection([ROW], [ROW]))
    assert embedder.encoded == [QUERY]
