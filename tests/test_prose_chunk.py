from ingestion.prose.chunk import chunk_article, pack_chunks, split_sections

WIKITEXT = """The '''2022 FIFA World Cup''' was an international [[football]] tournament held in [[Qatar]].<ref>Some citation.</ref> It was won by {{nowrap|Argentina}}.

== Venues ==
Eight stadiums hosted matches.

The largest was Lusail Stadium.

== Group standings ==
{| class="wikitable"
|-
! Team !! Points
|-
| Argentina || 6
|}

== Final ==
Argentina beat France on penalties.

== See also ==
* [[Football at the Olympics]]

== References ==
{{reflist}}
"""


def count_words(text):
    return len(text.split())


def test_lead_section_is_introduction():
    sections = split_sections(WIKITEXT)
    assert sections[0][0] == "Introduction"
    assert "2022 FIFA World Cup" in sections[0][1]


def test_markup_and_refs_are_stripped():
    _, lead = split_sections(WIKITEXT)[0]
    assert "'''" not in lead
    assert "[[" not in lead
    assert "Some citation" not in lead
    assert "{{" not in lead  # templates are dropped wholesale by strip_code


def test_prose_sections_are_extracted():
    headings = [heading for heading, _ in split_sections(WIKITEXT)]
    assert "Venues" in headings
    assert "Final" in headings


def test_table_only_and_boilerplate_sections_are_dropped():
    headings = [heading for heading, _ in split_sections(WIKITEXT)]
    assert "Group standings" not in headings
    assert "See also" not in headings
    assert "References" not in headings


def test_ref_nested_inside_template_does_not_crash():
    text = "Intro sentence.{{Infobox|note=<ref>nested cite</ref>}}\n\n== Final ==\nProse here."
    sections = split_sections(text)
    assert ("Final", "Prose here.") in sections


def test_short_section_stays_one_chunk():
    chunks = pack_chunks(["one two", "three four"], count_words, max_tokens=10)
    assert chunks == ["one two\nthree four"]


def test_long_section_splits_at_paragraph_boundaries():
    paragraphs = ["a b c d", "e f g h", "i j k l"]
    chunks = pack_chunks(paragraphs, count_words, max_tokens=8)
    assert chunks == ["a b c d\ne f g h", "i j k l"]


def test_oversized_paragraph_kept_whole():
    chunks = pack_chunks(["one two three four five"], count_words, max_tokens=3)
    assert chunks == ["one two three four five"]


def test_chunk_article_yields_indexed_chunks():
    chunks = chunk_article(WIKITEXT, count_words, max_tokens=256)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    sections = {c.section for c in chunks}
    assert {"Introduction", "Venues", "Final"} == sections
    final = next(c for c in chunks if c.section == "Final")
    assert final.content == "Argentina beat France on penalties."
