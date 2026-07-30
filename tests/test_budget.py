from ingestion.football.budget import select_fixtures_to_fetch


def test_returns_missing_ids_sorted_ascending():
    result = select_fixtures_to_fetch(
        all_fixture_ids={30, 10, 20}, loaded_fixture_ids=set(), budget=10
    )
    assert result == [10, 20, 30]


def test_excludes_already_loaded():
    result = select_fixtures_to_fetch(
        all_fixture_ids={10, 20, 30}, loaded_fixture_ids={20}, budget=10
    )
    assert result == [10, 30]


def test_caps_at_budget_taking_lowest_ids_first():
    result = select_fixtures_to_fetch(
        all_fixture_ids={10, 20, 30, 40}, loaded_fixture_ids=set(), budget=2
    )
    assert result == [10, 20]


def test_zero_remaining_returns_empty():
    result = select_fixtures_to_fetch(
        all_fixture_ids={10, 20}, loaded_fixture_ids={10, 20}, budget=5
    )
    assert result == []


def test_zero_budget_returns_empty():
    result = select_fixtures_to_fetch(
        all_fixture_ids={10, 20}, loaded_fixture_ids=set(), budget=0
    )
    assert result == []


def test_loaded_ids_not_in_fixtures_are_ignored():
    # e.g. a fixture was removed/rescheduled upstream after its lineup loaded
    result = select_fixtures_to_fetch(
        all_fixture_ids={10}, loaded_fixture_ids={10, 99}, budget=5
    )
    assert result == []
