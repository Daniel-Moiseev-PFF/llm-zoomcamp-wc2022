"""Tag chunks with the teams they mention, keyed by API-Football team names."""

import re

# API-Football names whose Wikipedia-prose spelling differs. Known-imperfect
# (demonyms like "Iranian" are deliberately not matched); good enough for a
# filter tag.
ALIASES = {
    "USA": ["USA", "United States"],
    "South Korea": ["South Korea", "Korea Republic"],
}


def teams_mentioned(text: str, team_names: list[str]) -> list[str]:
    found = []
    for name in team_names:
        variants = ALIASES.get(name, [name])
        if any(re.search(rf"\b{re.escape(v)}\b", text) for v in variants):
            found.append(name)
    return found
