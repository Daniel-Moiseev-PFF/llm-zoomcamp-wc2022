import csv

import pytest

from evaluation.retrieval import (
    RRF_K_SWEEP,
    CachingEmbedder,
    arm_search_functions,
    load_ground_truth,
    score_all,
    validate_ground_truth,
    write_csv,
)

# (article, section, chunk_index, content, teams_mentioned, score)
ROWS = [
    ("Final", "Result", 0, "Argentina won.", [], 0.9),
    ("Final", "Squads", 0, "The squads.", [], 0.8),
]


class StubResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class StubConnection:
    """Answers every arm with the same rows — the metrics are not under test here."""

    def __init__(self, rows=ROWS):
        self.rows = rows
        self.queries = 0

    def execute(self, sql, params=None):
        self.queries += 1
        return StubResult(self.rows)


class CountingEmbedder:
    def __init__(self):
        self.encoded = []

    def encode(self, text):
        self.encoded.append(text)
        return [0.1, 0.2, 0.3]


GROUND_TRUTH = [
    {"question": "who won the final?", "key": ("Final", "Result", 0)},
    {"question": "who was in the squad?", "key": ("Final", "Squads", 0)},
]


def test_arms_hand_evaluate_natural_keys_not_result_dicts():
    arms = arm_search_functions(CountingEmbedder(), StubConnection())
    for name, search_function in arms.items():
        assert search_function("who won the final?") == [
            ("Final", "Result", 0),
            ("Final", "Squads", 0),
        ], name


def test_every_arm_is_scored_plus_the_whole_rrf_sweep():
    rows = score_all(GROUND_TRUTH, CountingEmbedder(), StubConnection())
    assert [(r["arm"], r["rrf_k"]) for r in rows] == [
        ("lexical", ""),
        ("vector", ""),
        *[("hybrid", k) for k in RRF_K_SWEEP],
    ]


def test_every_scored_row_reports_both_metrics_and_the_sample_size():
    for row in score_all(GROUND_TRUTH, CountingEmbedder(), StubConnection()):
        assert 0.0 <= row["hit_rate"] <= 1.0
        assert 0.0 <= row["mrr"] <= 1.0
        assert row["questions"] == 2


def test_each_question_is_embedded_once_across_every_arm_and_sweep_step():
    # Six scoring passes over the ground truth; re-embedding each question six
    # times is pure waste, and at ~600 questions it is the bulk of the runtime.
    embedder = CountingEmbedder()
    score_all(GROUND_TRUTH, embedder, StubConnection())
    assert sorted(embedder.encoded) == sorted(r["question"] for r in GROUND_TRUTH)


def test_the_lexical_arm_never_embeds():
    embedder = CountingEmbedder()
    arm_search_functions(embedder, StubConnection())["lexical"]("who won?")
    assert embedder.encoded == []


def test_caching_embedder_returns_the_same_vector_it_cached():
    embedder = CachingEmbedder(CountingEmbedder())
    assert embedder.encode("q") == embedder.encode("q") == [0.1, 0.2, 0.3]


def test_a_ground_truth_key_matching_no_chunk_is_an_error():
    # The corpus moved under the committed CSV. Silently scoring against a
    # shrunken gold set would understate every arm equally and invisibly.
    with pytest.raises(ValueError, match="Final"):
        validate_ground_truth(GROUND_TRUTH, {("Final", "Result", 0)})


def test_validation_passes_when_every_key_is_present():
    validate_ground_truth(
        GROUND_TRUTH, {("Final", "Result", 0), ("Final", "Squads", 0), ("Other", "x", 9)}
    )


def test_load_ground_truth_reads_chunk_index_back_as_an_integer(tmp_path):
    # csv gives strings; ("Final", "Result", "0") never equals ("Final",
    # "Result", 0), so every single query would score as a miss.
    path = tmp_path / "gt.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["article", "section", "chunk_index", "question"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "article": "Final",
                "section": "Result",
                "chunk_index": "3",
                "question": "who won?",
            }
        )
    assert load_ground_truth(path) == [
        {"question": "who won?", "key": ("Final", "Result", 3)}
    ]


def test_write_csv_round_trips_the_scored_rows(tmp_path):
    path = tmp_path / "metrics.csv"
    rows = score_all(GROUND_TRUTH, CountingEmbedder(), StubConnection())
    write_csv(rows, path)
    written = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(written) == len(rows)
    assert written[0]["arm"] == "lexical"
    assert set(written[0]) == {
        "arm", "rrf_k", "candidates", "hit_rate", "mrr", "questions",
    }


def test_the_hybrid_rows_record_the_candidate_depth_they_used():
    # Hybrid scores change with the pool depth, so a committed CSV without it
    # cannot be reproduced.
    rows = score_all(GROUND_TRUTH, CountingEmbedder(), StubConnection(), k=5, candidates=20)
    hybrid = [r for r in rows if r["arm"] == "hybrid"]
    assert {r["candidates"] for r in hybrid} == {20}
