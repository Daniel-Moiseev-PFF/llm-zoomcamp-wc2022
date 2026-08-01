import dlt
import pytest

# --- Canned API-Football response payloads (the `response` array only) ---

TEAMS_RESPONSE = [
    {
        "team": {
            "id": 25, "name": "Germany", "code": "GER", "country": "Germany",
            "founded": 1900, "national": True, "logo": "https://example/25.png",
        },
        "venue": {
            "id": 556, "name": "Estadio Azteca", "address": "Calz. de Tlalpan",
            "city": "Mexico City", "capacity": 87523, "surface": "grass",
            "image": "https://example/556.png",
        },
    },
    {
        "team": {
            "id": 26, "name": "Scotland", "code": "SCO", "country": "Scotland",
            "founded": 1873, "national": True, "logo": "https://example/26.png",
        },
        "venue": {
            "id": 557, "name": "MetLife Stadium", "address": "1 MetLife Stadium Dr",
            "city": "East Rutherford", "capacity": 82500, "surface": "grass",
            "image": "https://example/557.png",
        },
    },
]

def _stats(played, win, draw, lose, goals_for, goals_against):
    return {
        "played": played, "win": win, "draw": draw, "lose": lose,
        "goals": {"for": goals_for, "against": goals_against},
    }

STANDINGS_RESPONSE = [
    {
        "league": {
            "id": 1, "name": "World Cup", "country": "World",
            "logo": "https://example/league1.png", "flag": None, "season": 2026,
            "standings": [
                [
                    {
                        "rank": 1,
                        "team": {"id": 25, "name": "Germany", "logo": "https://example/25.png"},
                        "points": 9, "goalsDiff": 5, "group": "Group A",
                        "form": "WWW", "status": "same", "description": None,
                        "all": _stats(3, 3, 0, 0, 7, 2),
                        "home": _stats(2, 2, 0, 0, 5, 1),
                        "away": _stats(1, 1, 0, 0, 2, 1),
                        "update": "2026-06-20T00:00:00+00:00",
                    },
                    {
                        "rank": 2,
                        "team": {"id": 26, "name": "Scotland", "logo": "https://example/26.png"},
                        "points": 4, "goalsDiff": -1, "group": "Group A",
                        "form": "WDL", "status": "same", "description": None,
                        "all": _stats(3, 1, 1, 1, 3, 4),
                        "home": _stats(1, 0, 1, 0, 1, 1),
                        "away": _stats(2, 1, 0, 1, 2, 3),
                        "update": "2026-06-20T00:00:00+00:00",
                    },
                ],
                [
                    {
                        "rank": 1,
                        "team": {"id": 27, "name": "Japan", "logo": "https://example/27.png"},
                        "points": 7, "goalsDiff": 3, "group": "Group B",
                        "form": "WWD", "status": "same", "description": None,
                        "all": _stats(3, 2, 1, 0, 5, 2),
                        "home": _stats(2, 1, 1, 0, 3, 1),
                        "away": _stats(1, 1, 0, 0, 2, 1),
                        "update": "2026-06-20T00:00:00+00:00",
                    },
                ],
            ],
        }
    }
]

def _fixture(fixture_id, date, home, away):
    return {
        "fixture": {
            "id": fixture_id, "referee": "Some Ref", "timezone": "UTC",
            "date": date, "timestamp": 1780000000,
            "venue": {"id": 556, "name": "Estadio Azteca", "city": "Mexico City"},
            "status": {"long": "Match Finished", "short": "FT", "elapsed": 90},
        },
        "league": {
            "id": 1, "name": "World Cup", "country": "World", "season": 2026,
            "round": "Group Stage - 1",
        },
        "teams": {
            "home": {"id": home[0], "name": home[1], "winner": True},
            "away": {"id": away[0], "name": away[1], "winner": False},
        },
        "goals": {"home": 2, "away": 0},
        "score": {
            "halftime": {"home": 1, "away": 0},
            "fulltime": {"home": 2, "away": 0},
            "extratime": {"home": None, "away": None},
            "penalty": {"home": None, "away": None},
        },
    }

FIXTURES_RESPONSE = [
    _fixture(1001, "2026-06-11T20:00:00+00:00", (25, "Germany"), (26, "Scotland")),
    _fixture(1002, "2026-06-12T20:00:00+00:00", (27, "Japan"), (25, "Germany")),
]

def _player(player_id, name, number, pos, grid):
    return {"player": {"id": player_id, "name": name, "number": number, "pos": pos, "grid": grid}}

def _lineup(team_id, team_name, formation, start_ids, sub_ids):
    return {
        "team": {
            "id": team_id, "name": team_name, "logo": f"https://example/{team_id}.png",
            "colors": {
                "player": {"primary": "ffffff", "number": "000000", "border": "ffffff"},
                "goalkeeper": {"primary": "00ff00", "number": "000000", "border": "00ff00"},
            },
        },
        "coach": {"id": team_id * 10, "name": f"Coach {team_name}", "photo": ""},
        "formation": formation,
        "startXI": [
            _player(pid, f"Player {pid}", i + 1, "G" if i == 0 else "M", f"{i + 1}:1")
            for i, pid in enumerate(start_ids)
        ],
        "substitutes": [
            _player(pid, f"Player {pid}", 12 + i, "S", None)
            for i, pid in enumerate(sub_ids)
        ],
    }

LINEUPS_RESPONSES = {
    1001: [
        _lineup(25, "Germany", "4-3-3", [101, 102], [103]),
        _lineup(26, "Scotland", "4-4-2", [201, 202], [203]),
    ],
    1002: [
        _lineup(27, "Japan", "4-2-3-1", [301, 302], [303]),
        _lineup(25, "Germany", "4-3-3", [101, 104], [105]),
    ],
}

def _event(elapsed, extra, team, event_type, detail, player, assist=(None, None)):
    return {
        "time": {"elapsed": elapsed, "extra": extra},
        "team": {"id": team[0], "name": team[1], "logo": f"https://example/{team[0]}.png"},
        "player": {"id": player[0], "name": player[1]},
        "assist": {"id": assist[0], "name": assist[1]},
        "type": event_type,
        "detail": detail,
        "comments": None,
    }

EVENTS_RESPONSES = {
    1001: [
        _event(25, None, (25, "Germany"), "Goal", "Normal Goal", (101, "Player 101")),
        # player = the one going off, assist = the one coming on
        _event(46, None, (25, "Germany"), "subst", "Substitution 1",
               (102, "Player 102"), (103, "Player 103")),
        _event(90, 3, (26, "Scotland"), "subst", "Substitution 1",
               (201, "Player 201"), (203, "Player 203")),
    ],
    1002: [
        _event(60, None, (27, "Japan"), "Card", "Yellow Card", (301, "Player 301")),
    ],
}


class FakeClient:
    """Duck-typed stand-in for ApiFootballClient. Never touches the network."""

    def __init__(self, teams=None, standings=None, fixtures=None, lineups=None,
                 lineup_errors=None, events=None, event_errors=None):
        self.teams = teams if teams is not None else TEAMS_RESPONSE
        self.standings = standings if standings is not None else STANDINGS_RESPONSE
        self.fixtures = fixtures if fixtures is not None else FIXTURES_RESPONSE
        self.lineups = lineups if lineups is not None else LINEUPS_RESPONSES
        self.lineup_errors = lineup_errors or {}
        self.events = events if events is not None else EVENTS_RESPONSES
        self.event_errors = event_errors or {}
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == "/teams":
            return self.teams
        if path == "/standings":
            return self.standings
        if path == "/fixtures":
            return self.fixtures
        if path == "/fixtures/lineups":
            fixture_id = params["fixture"]
            if fixture_id in self.lineup_errors:
                raise self.lineup_errors[fixture_id]
            return self.lineups[fixture_id]
        if path == "/fixtures/events":
            fixture_id = params["fixture"]
            if fixture_id in self.event_errors:
                raise self.event_errors[fixture_id]
            return self.events[fixture_id]
        raise AssertionError(f"FakeClient got unexpected path: {path}")

    def lineup_call_count(self):
        return sum(1 for path, _ in self.calls if path == "/fixtures/lineups")

    def event_call_count(self):
        return sum(1 for path, _ in self.calls if path == "/fixtures/events")


@pytest.fixture
def fake_client():
    return FakeClient()


@pytest.fixture
def duckdb_pipeline(tmp_path):
    return dlt.pipeline(
        pipeline_name="test_football",
        destination=dlt.destinations.duckdb(str(tmp_path / "test.duckdb")),
        dataset_name="football",
        pipelines_dir=str(tmp_path / "dlt_pipelines"),
    )


def table_counts(pipeline, *tables):
    counts = {}
    with pipeline.sql_client() as client:
        for table in tables:
            qualified = client.make_qualified_table_name(table)
            counts[table] = client.execute_sql(f"SELECT count(*) FROM {qualified}")[0][0]
    return counts
