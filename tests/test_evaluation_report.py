import csv

from evaluation.report import (
    answer_winner,
    load_csv,
    render,
    retrieval_winner,
)

RETRIEVAL = [
    {"arm": "lexical", "rrf_k": "", "hit_rate": 0.60, "mrr": 0.44, "questions": "600"},
    {"arm": "vector", "rrf_k": "", "hit_rate": 0.78, "mrr": 0.61, "questions": "600"},
    {"arm": "hybrid", "rrf_k": "1", "hit_rate": 0.83, "mrr": 0.69, "questions": "600"},
    {"arm": "hybrid", "rrf_k": "60", "hit_rate": 0.81, "mrr": 0.66, "questions": "600"},
]

ANSWERS = [
    {
        "variant": "full", "answers": "30", "CORRECT": "24", "PARTLY_CORRECT": "4",
        "INCORRECT": "2", "MISSING": "0", "correct_share": 0.80,
        "routed_as_expected": "27", "mean_cost": 0.0021, "mean_tokens": 9000.0,
        "mean_latency": 3.8,
    },
    {
        "variant": "lean", "answers": "30", "CORRECT": "20", "PARTLY_CORRECT": "6",
        "INCORRECT": "3", "MISSING": "1", "correct_share": 0.667,
        "routed_as_expected": "24", "mean_cost": 0.0016, "mean_tokens": 7000.0,
        "mean_latency": 3.2,
    },
]


def test_the_retrieval_winner_is_the_best_mrr():
    winner = retrieval_winner(RETRIEVAL)
    assert winner["arm"] == "hybrid"
    assert winner["rrf_k"] == "1"


def test_a_retrieval_tie_on_mrr_falls_back_to_hit_rate():
    rows = [
        {"arm": "vector", "rrf_k": "", "hit_rate": 0.70, "mrr": 0.61},
        {"arm": "hybrid", "rrf_k": "1", "hit_rate": 0.90, "mrr": 0.61},
    ]
    assert retrieval_winner(rows)["arm"] == "hybrid"


def test_a_full_retrieval_tie_prefers_the_simpler_arm():
    # Nothing to gain from fusing two arms that score exactly like one of them.
    rows = [
        {"arm": "hybrid", "rrf_k": "1", "hit_rate": 0.80, "mrr": 0.61},
        {"arm": "lexical", "rrf_k": "", "hit_rate": 0.80, "mrr": 0.61},
    ]
    assert retrieval_winner(rows)["arm"] == "lexical"


def test_the_answer_winner_is_the_best_correct_share():
    assert answer_winner(ANSWERS)["variant"] == "full"


def test_an_answer_tie_is_broken_by_cost():
    rows = [
        {"variant": "full", "correct_share": 0.80, "mean_cost": 0.0021},
        {"variant": "lean", "correct_share": 0.80, "mean_cost": 0.0016},
    ]
    assert answer_winner(rows)["variant"] == "lean"


def test_the_report_names_both_winners_and_where_each_was_wired():
    report = render(RETRIEVAL, ANSWERS)
    assert "hybrid" in report
    assert "full" in report
    assert "DEFAULT_ARM" in report
    assert "agent/instructions.py" in report


def test_the_report_shows_every_arm_and_every_variant_not_just_the_winners():
    # A reader has to be able to disagree with the pick.
    report = render(RETRIEVAL, ANSWERS)
    for arm in ("lexical", "vector", "hybrid"):
        assert arm in report
    for variant in ("full", "lean"):
        assert variant in report


def test_the_report_surfaces_missing_verdicts():
    # Hiding them would let a variant look better for failing to be scored.
    assert "MISSING" in render(RETRIEVAL, ANSWERS)


def test_the_report_states_both_caveats():
    report = render(RETRIEVAL, ANSWERS).lower()
    assert "synthetic" in report  # generated questions bias the lexical arm
    assert "by hand" in report or "hand-curated" in report


def test_the_report_says_it_is_generated():
    assert "evaluation/report.py" in render(RETRIEVAL, ANSWERS)


def test_load_csv_coerces_the_numeric_columns(tmp_path):
    path = tmp_path / "metrics.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["arm", "hit_rate", "mrr"])
        writer.writeheader()
        writer.writerow({"arm": "vector", "hit_rate": "0.78", "mrr": "0.61"})
    rows = load_csv(path, numeric=("hit_rate", "mrr"))
    assert rows[0]["mrr"] == 0.61
