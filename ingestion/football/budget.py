"""Pure resumability math: which lineup fetches fit in this run's budget."""

from collections.abc import Iterable


def select_fixtures_to_fetch(
    all_fixture_ids: Iterable[int],
    loaded_fixture_ids: Iterable[int],
    budget: int,
) -> list[int]:
    remaining = sorted(set(all_fixture_ids) - set(loaded_fixture_ids))
    return remaining[: max(budget, 0)]
