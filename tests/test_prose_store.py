from ingestion.prose import EMBEDDING_DIM
from ingestion.prose.chunk import Chunk
from ingestion.prose.manifest import Article
from ingestion.prose.store import CREATE_TABLE_SQL, chunk_row, vec_to_str


def test_vec_to_str_formats_pgvector_literal():
    assert vec_to_str([0.1, -0.2, 1.0]) == "[0.1,-0.2,1.0]"


def test_create_table_uses_model_dimension():
    assert f"vector({EMBEDDING_DIM})" in CREATE_TABLE_SQL


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
