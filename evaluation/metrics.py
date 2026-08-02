"""Retrieval metrics — llm-zoomcamp 04-evaluation/lessons/05-search-metrics.md.

A "relevance list" is one list per query of 0/1 flags, in rank order: a 1 marks
the position where the gold document was found. Each query here has exactly one
gold document, so Hit Rate and Recall@k coincide.
"""


def hit_rate(relevance) -> float:
    """Fraction of queries whose gold document appears anywhere in the results.

    Args:
        relevance: list of per-query 0/1 lists in rank order.

    Returns:
        Hits divided by number of queries; 0.0 for an empty input.
    """
    raise NotImplementedError


def mrr(relevance) -> float:
    """Mean Reciprocal Rank: the mean of 1/(rank of the first hit).

    Rank is 1-based, so a hit in the first position scores 1.0, the second
    0.5, the third 1/3. A query that found nothing contributes 0.

    Args:
        relevance: list of per-query 0/1 lists in rank order.

    Returns:
        The mean reciprocal rank; 0.0 for an empty input.
    """
    raise NotImplementedError


def evaluate(ground_truth, search_function) -> dict:
    """Score one search function over the ground truth.

    Calls search_function(question) for every ground-truth row, turns each
    result list into a 0/1 relevance list by comparing each returned key
    against that row's gold ``key``, then reduces with hit_rate and mrr.

    Args:
        ground_truth: rows of {"question": str, "key": hashable gold key}.
        search_function: question -> list of keys, best first.

    Returns:
        {"hit_rate": float, "mrr": float}
    """
    raise NotImplementedError
