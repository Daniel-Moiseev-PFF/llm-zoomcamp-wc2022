"""Score the three retrieval arms against the generated ground truth.

Follows llm-zoomcamp 04-evaluation/lessons/04-search-evaluation.md: wrap each
arm as a question -> results function and hand it to `evaluate`. The RRF k
sweep comes from best-practices lesson 02, where k is the knob that decides how
much rank position matters when the two arms disagree.

  uv run python -m evaluation.retrieval [--k 5] [--candidates N]
"""

import argparse
import csv

from evaluation import DATA_DIR
from evaluation.ground_truth import GROUND_TRUTH_PATH
from evaluation.metrics import evaluate
from ingestion.prose.search import (
    natural_key,
    search_hybrid,
    search_lexical,
    search_vector,
)

METRICS_PATH = DATA_DIR / "retrieval-metrics.csv"
FIELDNAMES = ["arm", "rrf_k", "candidates", "hit_rate", "mrr", "questions"]

# k smooths the difference between rank positions: at k=1 the top hit dominates,
# at k=60 (the value the original RRF paper uses) the lists are nearly equal
# votes. Which one suits this corpus is exactly what the sweep answers.
RRF_K_SWEEP = (1, 5, 20, 60)

DEFAULT_K = 5


class CachingEmbedder:
    """Embeds each distinct question once, then hands the same vector to every arm.

    Six scoring passes over ~600 questions would otherwise mean ~3,600
    encodes for ~600 distinct strings.
    """

    def __init__(self, embedder):
        self._embedder = embedder
        self._cache: dict[str, list] = {}

    def encode(self, text):
        if text not in self._cache:
            self._cache[text] = self._embedder.encode(text)
        return self._cache[text]


def keys(results) -> list[tuple]:
    return [natural_key(result) for result in results]


def arm_search_functions(embedder, conn, k=DEFAULT_K, candidates=None, rrf_k=1) -> dict:
    """Each arm as a question -> [natural key] function, ready for `evaluate`."""
    return {
        "lexical": lambda q: keys(search_lexical(q, conn, k=k)),
        "vector": lambda q: keys(search_vector(q, embedder, conn, k=k)),
        "hybrid": lambda q: keys(
            search_hybrid(
                q, embedder, conn, k=k, candidates=candidates or k, rrf_k=rrf_k
            )
        ),
    }


def score_all(
    ground_truth, embedder, conn, k=DEFAULT_K, candidates=None, sweep=RRF_K_SWEEP
) -> list[dict]:
    """One row per arm, plus one hybrid row per swept RRF k."""
    cached = CachingEmbedder(embedder)
    rows = []
    single_arms = arm_search_functions(cached, conn, k=k, candidates=candidates)
    for name in ("lexical", "vector"):
        rows.append(
            {
                "arm": name,
                "rrf_k": "",
                "candidates": "",  # only the fused arm reads a deeper pool
                **evaluate(ground_truth, single_arms[name]),
                "questions": len(ground_truth),
            }
        )
    for rrf_k in sweep:
        hybrid = arm_search_functions(
            cached, conn, k=k, candidates=candidates, rrf_k=rrf_k
        )["hybrid"]
        rows.append(
            {
                "arm": "hybrid",
                "rrf_k": rrf_k,
                "candidates": candidates or k,
                **evaluate(ground_truth, hybrid),
                "questions": len(ground_truth),
            }
        )
    return rows


def load_ground_truth(path=GROUND_TRUTH_PATH) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [
            {
                "question": row["question"],
                "key": (row["article"], row["section"], int(row["chunk_index"])),
            }
            for row in csv.DictReader(handle)
        ]


def chunk_keys(conn) -> set[tuple]:
    rows = conn.execute("SELECT article, section, chunk_index FROM prose.chunks")
    return {tuple(row) for row in rows.fetchall()}


def validate_ground_truth(ground_truth, known_keys) -> None:
    """Fail loudly if the corpus moved under the committed ground truth.

    A missing gold document can never be retrieved, so it drags every arm down
    by the same amount — the comparison still looks plausible while every
    number in it is wrong.
    """
    missing = {row["key"] for row in ground_truth} - set(known_keys)
    if missing:
        sample = sorted(missing)[:5]
        raise ValueError(
            f"{len(missing)} ground-truth keys match no chunk, e.g. {sample}. "
            "Re-run evaluation.ground_truth against the current corpus."
        )


def write_csv(rows, path=METRICS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows) -> None:
    header = f"{'arm':<9} {'rrf_k':>6} {'cands':>6} {'hit_rate':>9} {'mrr':>7} {'questions':>10}"
    print(header)
    for row in rows:
        print(
            f"{row['arm']:<9} {str(row['rrf_k']):>6} {str(row['candidates']):>6} "
            f"{row['hit_rate']:>9.4f} {row['mrr']:>7.4f} {row['questions']:>10}"
        )


def main() -> None:
    from dotenv import load_dotenv

    from ingestion.prose import MODEL_PATH
    from ingestion.prose.embedder import Embedder
    from ingestion.prose.store import connect

    load_dotenv()

    parser = argparse.ArgumentParser(description="Compare the three retrieval arms.")
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="results per query")
    parser.add_argument(
        "--candidates", type=int, default=None, help="depth read per arm before fusing"
    )
    args = parser.parse_args()

    ground_truth = load_ground_truth()
    print(f"{len(ground_truth)} ground-truth questions")

    with connect() as conn:
        validate_ground_truth(ground_truth, chunk_keys(conn))
        rows = score_all(
            ground_truth,
            Embedder(MODEL_PATH),
            conn,
            k=args.k,
            candidates=args.candidates,
        )

    print_table(rows)
    write_csv(rows)
    print(f"\n-> {METRICS_PATH}")


if __name__ == "__main__":
    main()
