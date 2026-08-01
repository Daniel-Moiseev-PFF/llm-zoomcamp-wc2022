from ingestion.prose.tag import teams_mentioned

TEAM_NAMES = ["Argentina", "France", "Iran", "Mexico", "USA", "Wales"]


def test_matches_teams_in_text():
    text = "Argentina beat France on penalties in the final."
    assert teams_mentioned(text, TEAM_NAMES) == ["Argentina", "France"]


def test_no_teams_returns_empty():
    assert teams_mentioned("The stadium roof stayed open.", TEAM_NAMES) == []


def test_usa_alias_matches_united_states():
    text = "The United States drew with Wales in Group B."
    assert teams_mentioned(text, TEAM_NAMES) == ["USA", "Wales"]


def test_word_boundary_prevents_partial_matches():
    # "Iranian" should not tag Iran; a plain mention should.
    assert teams_mentioned("Iranian broadcasters cut the feed.", TEAM_NAMES) == []
    assert teams_mentioned("Iran faced England.", TEAM_NAMES) == ["Iran"]
