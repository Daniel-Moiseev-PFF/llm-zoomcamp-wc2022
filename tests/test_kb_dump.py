"""The knowledge base ships as a committed artifact, so it gets tested like one.

Each assertion here is a restore-breaker or a silent-wrongness guard, verified
against a real dump before being written down. Pure file reads — no database.
"""

import gzip
import re
from pathlib import Path

import pytest

from ingestion.prose import EMBEDDING_DIM

ROOT = Path(__file__).resolve().parent.parent
DUMP_PATH = ROOT / "data" / "kb.sql.gz"
EXTENSIONS_PATH = ROOT / "docker" / "initdb" / "00-extensions.sql"

# Every table the README promises a reviewer will find populated. The two
# lineups child tables are where the players live — the self-join the README
# leads with ("did X and Y play against each other?") reads them, not the
# parent.
REQUIRED_TABLES = (
    "football.teams",
    "football.fixtures",
    "football.events",
    "football.standings",
    "football.lineups",
    "football.lineups__start_xi",
    "football.lineups__substitutes",
    "prose.chunks",
)


@pytest.fixture(scope="module")
def dump():
    with gzip.open(DUMP_PATH, "rt", encoding="utf-8") as handle:
        return handle.read()


def test_the_dump_declares_the_dimension_the_embedder_produces(dump):
    # A change to the embedding model would leave this dump loadable but wrong:
    # every vector search would return nonsense against mismatched dimensions.
    assert f"vector({EMBEDDING_DIM})" in dump


def test_every_promised_table_carries_rows(dump):
    for table in REQUIRED_TABLES:
        copy = re.search(rf"^COPY {re.escape(table)} \(.*$", dump, re.MULTILINE)
        assert copy, f"no COPY block for {table}"
        body = dump[copy.end():].split("\\.", 1)[0]
        assert body.strip(), f"{table} was dumped empty"


def test_the_dump_restores_under_any_database_user(dump):
    # POSTGRES_USER comes from the reviewer's own .env and will not match the
    # user that produced the dump.
    for statement in ("OWNER TO", "GRANT ", "REVOKE "):
        assert statement not in dump


def test_the_generated_column_is_not_copied(dump):
    # content_tsv is GENERATED ALWAYS AS ... STORED; copying into it fails.
    copy = re.search(r"^COPY prose\.chunks \((.*)\)", dump, re.MULTILINE)
    assert copy
    assert "content_tsv" not in copy.group(1)


def test_the_lineups_child_join_keys_survive_the_dump(dump):
    # agent/instructions.py joins lineups__start_xi._dlt_parent_id to
    # lineups._dlt_id. Losing dlt's internal columns would restore cleanly and
    # silently break the query the README leads with.
    parent = re.search(r"^COPY football\.lineups \((.*)\)", dump, re.MULTILINE)
    child = re.search(
        r"^COPY football\.lineups__start_xi \((.*)\)", dump, re.MULTILINE
    )
    assert parent and child
    assert "_dlt_id" in parent.group(1)
    assert "_dlt_parent_id" in child.group(1)


def test_monitoring_traffic_is_not_shipped(dump):
    # Seeded rows are back-dated relative to now, so a dump of them renders an
    # empty dashboard within a day. The seed service regenerates them instead.
    assert "CREATE SCHEMA monitoring" not in dump


def test_the_vector_extension_is_created_separately(dump):
    # Extensions live in public, so --schema= excludes them: the dump references
    # public.vector(384) but cannot create it.
    assert "CREATE EXTENSION" not in dump
    assert "vector" in EXTENSIONS_PATH.read_text().lower()
