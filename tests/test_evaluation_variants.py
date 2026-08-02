from agent.instructions import INSTRUCTIONS
from evaluation.variants import VARIANTS

# Every table the agent can query. Dropping coaching from a variant must not
# quietly drop the schema — that would measure the wrong thing.
FOOTBALL_TABLES = [
    "football.teams",
    "football.standings",
    "football.fixtures",
    "football.lineups",
    "football.lineups__start_xi",
    "football.lineups__substitutes",
    "football.events",
]


def test_there_are_three_named_variants():
    assert set(VARIANTS) == {"full", "lean", "guided"}


def test_every_variant_is_a_non_empty_prompt():
    for name, prompt in VARIANTS.items():
        assert prompt.strip(), name


def test_the_variants_are_actually_different():
    # Three identical prompts would produce three identical scores and prove
    # nothing about prompt design.
    assert len(set(VARIANTS.values())) == 3


def test_full_is_the_shipped_prompt_itself_not_a_copy():
    # A copy would drift silently the next time agent/instructions.py changes,
    # and the evaluation would report on a prompt nothing actually runs.
    assert VARIANTS["full"] is INSTRUCTIONS


def test_lean_is_materially_shorter_than_full():
    assert len(VARIANTS["lean"]) < len(VARIANTS["full"]) * 0.75


def test_lean_drops_the_coaching_but_keeps_the_schema():
    lean = VARIANTS["lean"]
    for table in FOOTBALL_TABLES:
        assert table in lean, table
    assert "ILIKE" not in lean
    assert "COMING OFF" not in lean
    assert "Mbapp" not in lean  # the worked self-join example


def test_lean_still_routes():
    # It is the "no coaching" arm, not the "no instructions" arm.
    lean = VARIANTS["lean"]
    for tool in ("execute_sql", "search_prose", "read_section"):
        assert tool in lean, tool


def test_guided_extends_full_rather_than_replacing_it():
    assert VARIANTS["full"] in VARIANTS["guided"]
    assert len(VARIANTS["guided"]) > len(VARIANTS["full"])


def test_guided_demonstrates_answering_both_halves_of_a_mixed_question():
    # The failure mode it targets: the agent calls one tool, gets a good
    # result, and answers before touching the other half of the question.
    assert "both" in VARIANTS["guided"].lower()
