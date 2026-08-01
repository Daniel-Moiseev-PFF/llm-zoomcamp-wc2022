"""Curated Wikipedia articles for the prose corpus, pinned to revision ids.

Pinned 2026-07-31 so the corpus is reproducible and doesn't drift as
Wikipedia keeps updating. The season is Qatar 2022 to match the structured
data (see ingestion/football/__init__.py).
"""

from typing import NamedTuple


class Article(NamedTuple):
    title: str
    oldid: int


ARTICLES = [
    Article("2022 FIFA World Cup", 1366281110),
    Article("2022 FIFA World Cup final", 1366872824),
    Article("2022 FIFA World Cup knockout stage", 1365744402),
    Article("2022 FIFA World Cup opening ceremony", 1363770015),
    Article("List of 2022 FIFA World Cup controversies", 1366541800),
]
