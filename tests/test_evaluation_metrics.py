import pytest

from evaluation.metrics import evaluate, hit_rate, mrr

# llm-zoomcamp 04-evaluation/lessons/05-search-metrics.md, verbatim.
# 15 queries, one relevant document each; 14 of them found it.
LESSON_EXAMPLE = [
    [1, 0, 0, 0, 0],
    [0, 1, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 1, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [0, 0, 1, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
]


def test_hit_rate_matches_the_lesson_worked_example():
    assert hit_rate(LESSON_EXAMPLE) == pytest.approx(14 / 15)


def test_hit_rate_counts_a_query_once_even_with_several_hits():
    # Hit Rate is "did we find it at all", not "how many did we find".
    assert hit_rate([[1, 1, 1]]) == pytest.approx(1.0)


def test_hit_rate_is_zero_when_nothing_is_ever_found():
    assert hit_rate([[0, 0], [0, 0]]) == pytest.approx(0.0)


def test_mrr_scores_by_the_rank_of_the_first_hit():
    # rank 1 -> 1/1, rank 2 -> 1/2, rank 3 -> 1/3; mean of the three.
    relevance = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert mrr(relevance) == pytest.approx((1 + 0.5 + 1 / 3) / 3)


def test_mrr_ignores_hits_after_the_first():
    # Only the first hit counts, so this must score the same as [1, 0, 0].
    assert mrr([[1, 1, 1]]) == pytest.approx(1.0)


def test_mrr_contributes_zero_for_a_query_that_found_nothing():
    assert mrr([[1, 0], [0, 0]]) == pytest.approx(0.5)


def test_evaluate_builds_relevance_by_comparing_search_results_to_the_gold_key():
    ground_truth = [
        {"question": "who won the final?", "key": ("Final", "Result", 0)},
        {"question": "who opened the ceremony?", "key": ("Ceremony", "Acts", 1)},
    ]

    def fake_search(question):
        # First question: gold document second. Second question: missed.
        if question == "who won the final?":
            return [("Final", "Squads", 0), ("Final", "Result", 0)]
        return [("Ceremony", "Venue", 0)]

    result = evaluate(ground_truth, fake_search)

    assert result["hit_rate"] == pytest.approx(0.5)
    assert result["mrr"] == pytest.approx(0.25)  # 1/2 for the first, 0 for the second


def test_evaluate_asks_the_search_function_for_every_question():
    asked = []
    ground_truth = [
        {"question": "a", "key": ("A", "s", 0)},
        {"question": "b", "key": ("B", "s", 0)},
    ]

    def recording_search(question):
        asked.append(question)
        return []

    evaluate(ground_truth, recording_search)

    assert asked == ["a", "b"]
