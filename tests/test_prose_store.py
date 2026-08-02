from ingestion.prose import EMBEDDING_DIM
from ingestion.prose.chunk import Chunk
from ingestion.prose.manifest import Article
from ingestion.prose.store import CREATE_TABLE_SQL, chunk_row, recreate_table, vec_to_str


class FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        assert params is None, "recreate_table issues DDL only"


def test_vec_to_str_formats_pgvector_literal():
    assert vec_to_str([0.1, -0.2, 1.0]) == "[0.1,-0.2,1.0]"


def test_create_table_uses_model_dimension():
    assert f"vector({EMBEDDING_DIM})" in CREATE_TABLE_SQL


def test_create_table_generates_the_lexical_search_column():
    # Generated + STORED, so the lexical arm can never search a stale tsvector:
    # Postgres recomputes it on write. This is only legal because to_tsvector
    # with an explicit regconfig is immutable.
    assert "content_tsv tsvector GENERATED ALWAYS AS" in CREATE_TABLE_SQL
    assert "STORED" in CREATE_TABLE_SQL


def test_lexical_column_weights_the_section_heading_above_the_body():
    # Section titles carry real signal in this corpus ("Controversies",
    # "Final"), so a query matching a heading should outrank a body mention.
    assert "setweight(to_tsvector('english', section), 'A')" in CREATE_TABLE_SQL
    assert "setweight(to_tsvector('english', content), 'B')" in CREATE_TABLE_SQL


def test_recreate_table_indexes_the_lexical_column_after_creating_the_table():
    conn = FakeConnection()
    recreate_table(conn)
    joined = "\n".join(conn.statements)
    assert "USING GIN (content_tsv)" in joined
    create = next(i for i, s in enumerate(conn.statements) if "CREATE TABLE" in s)
    index = next(i for i, s in enumerate(conn.statements) if "USING GIN" in s)
    assert create < index


def test_chunk_row_shapes_insert_values():
    article = Article("2022 FIFA World Cup final", 1366872824)
    chunk = Chunk(section="Summary", chunk_index=3, content="Argentina won.")
    row = chunk_row(article, chunk, ["Argentina", "France"], [0.5] * 3)
    assert row == (
        "2022 FIFA World Cup final",
        1366872824,
        "Summary",
        3,
        "Argentina won.",
        ["Argentina", "France"],
        "[0.5,0.5,0.5]",
    )
