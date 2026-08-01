"""Split article wikitext into embeddable prose chunks.

The rule from the README: sentences -> prose index; cells -> SQL. Tables and
boilerplate sections are dropped here; that data lives on the structured side.
"""

import logging
from typing import Callable, NamedTuple

import mwparserfromhell

logger = logging.getLogger(__name__)

# all-MiniLM-L6-v2 truncates input at 256 wordpieces, so longer sections must
# be split or their tails would never be embedded.
MAX_TOKENS = 256

_SKIP_HEADINGS = {
    "references",
    "external links",
    "see also",
    "notes",
    "bibliography",
    "further reading",
}
_SKIP_TAGS = {"table", "ref", "gallery", "timeline"}


class Chunk(NamedTuple):
    section: str
    chunk_index: int
    content: str


def _section_text(section) -> str:
    code = mwparserfromhell.parse(str(section))
    for node in code.filter_tags(matches=lambda tag: str(tag.tag) in _SKIP_TAGS):
        try:
            code.remove(node)
        except ValueError:
            # Nested inside a template or an already-removed node; strip_code
            # drops its container anyway.
            pass
    for heading in code.filter_headings():
        code.remove(heading)
    return code.strip_code(normalize=True, collapse=True).strip()


def split_sections(wikitext: str) -> list[tuple[str, str]]:
    code = mwparserfromhell.parse(wikitext)
    out = []
    for section in code.get_sections(levels=[2], include_lead=True):
        headings = section.filter_headings()
        heading = headings[0].title.strip_code().strip() if headings else "Introduction"
        if heading.lower() in _SKIP_HEADINGS:
            continue
        text = _section_text(section)
        if text:
            out.append((heading, text))
    return out


def pack_chunks(
    paragraphs: list[str], count_tokens: Callable[[str], int], max_tokens: int = MAX_TOKENS
) -> list[str]:
    """Greedily pack paragraphs into chunks of at most max_tokens.

    A single paragraph over the limit stays whole (the embedder truncates it).
    """
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for paragraph in paragraphs:
        tokens = count_tokens(paragraph)
        if tokens > max_tokens and not current:
            logger.warning(
                "Paragraph of %d tokens exceeds the %d-token limit; embedding truncated",
                tokens,
                max_tokens,
            )
        if current and current_tokens + tokens > max_tokens:
            chunks.append("\n".join(current))
            current, current_tokens = [], 0
        current.append(paragraph)
        current_tokens += tokens
    if current:
        chunks.append("\n".join(current))
    return chunks


def chunk_article(
    wikitext: str, count_tokens: Callable[[str], int], max_tokens: int = MAX_TOKENS
) -> list[Chunk]:
    chunks = []
    for heading, text in split_sections(wikitext):
        paragraphs = [line.strip() for line in text.split("\n") if line.strip()]
        for content in pack_chunks(paragraphs, count_tokens, max_tokens):
            chunks.append(Chunk(section=heading, chunk_index=len(chunks), content=content))
    return chunks
