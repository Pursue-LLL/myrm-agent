"""Unit tests for FTS schema migration, truth retention and the heal-and-retry path in fts_search."""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.vector.base import SearchResult, VectorDocument
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval import fts_search
from myrm_agent_harness.toolkits.wiki.retrieval.fts_search import migrate_wiki_fts_schema
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer
from myrm_agent_harness.toolkits.wiki.retrieval.tokenizer import tokenize_for_fts
from tests.support.fts5_corruption import CORRUPTIONS, corrupt_fts5_index


def _legacy_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE VIRTUAL TABLE wiki_fts USING fts5(
            concept_name,
            truth_content,
            tokenize="unicode61 remove_diacritics 1"
        )
    """
    )
    conn.execute(
        "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
        ("Legacy Concept", "legacy searchable content"),
    )
    conn.commit()
    return conn


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(wiki_fts)").fetchall()}


def test_migrates_legacy_schema_and_preserves_rows(tmp_path: Path) -> None:
    conn = _legacy_db(tmp_path / "legacy.db")
    try:
        assert _columns(conn) == {"concept_name", "truth_content"}

        migrate_wiki_fts_schema(conn)

        assert _columns(conn) == {"concept_name", "truth_content", "search_terms"}
        row = conn.execute(
            "SELECT truth_content, search_terms FROM wiki_fts WHERE concept_name = ?",
            ("Legacy Concept",),
        ).fetchone()
        assert row == ("legacy searchable content", "legacy searchable content")
    finally:
        conn.close()


def test_migration_is_idempotent_on_current_schema(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "current.db")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE wiki_fts USING fts5(
                concept_name,
                truth_content,
                search_terms,
                tokenize="unicode61 remove_diacritics 1"
            )
        """
        )
        conn.execute(
            "INSERT INTO wiki_fts (concept_name, truth_content, search_terms) VALUES (?, ?, ?)",
            ("Current Concept", "Original Truth", "original truth tokens"),
        )
        conn.commit()

        migrate_wiki_fts_schema(conn)

        row = conn.execute(
            "SELECT truth_content, search_terms FROM wiki_fts WHERE concept_name = ?",
            ("Current Concept",),
        ).fetchone()
        assert row == ("Original Truth", "original truth tokens")
    finally:
        conn.close()


async def _indexer_with_one_page(root: Path) -> WikiIndexer:
    structure = WikiStructure(root)
    structure.ensure_structure()
    indexer = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))
    await indexer.upsert("alpha", "---\ntype: concept\n---\n\n## Compiled Truth\nkelvin kelvin\n")
    return indexer


def _fail_building_the_query(monkeypatch: pytest.MonkeyPatch, *, failures: int) -> None:
    """Make the first ``failures`` builds of the match query raise, like a database that is locked for a moment."""
    real = fts_search._published_match_select
    calls = {"count": 0}

    def flaky(conn: sqlite3.Connection, fts_table: str, columns: str) -> str:
        calls["count"] += 1
        if calls["count"] <= failures:
            raise sqlite3.OperationalError("database is locked")
        return real(conn, fts_table, columns)

    monkeypatch.setattr(fts_search, "_published_match_select", flaky)


async def test_search_retries_after_a_heal_when_the_query_could_not_be_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    indexer = await _indexer_with_one_page(tmp_path / "vault")
    _fail_building_the_query(monkeypatch, failures=1)
    monkeypatch.setattr(fts_search, "fts5_auto_heal", lambda conn, table: True)

    results = await indexer.search("kelvin")

    assert [name for name, _ in results] == ["alpha"]


@pytest.mark.parametrize("healed", [True, False])
async def test_search_returns_nothing_when_the_query_keeps_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, healed: bool
) -> None:
    indexer = await _indexer_with_one_page(tmp_path / "vault")
    _fail_building_the_query(monkeypatch, failures=100)
    monkeypatch.setattr(fts_search, "fts5_auto_heal", lambda conn, table: healed)

    assert await indexer.search("kelvin") == []


async def _filled_indexer(root: Path, pages: int = 40) -> tuple[WikiStructure, WikiIndexer]:
    """An index of pages that all match "kelvin", big enough for its FTS5 table to own segment blocks."""
    structure = WikiStructure(root)
    structure.ensure_structure()
    indexer = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))
    for i in range(pages):
        await indexer.upsert(
            f"page-{i:02d}", f"---\ntype: concept\n---\n\n## Compiled Truth\n{'kelvin note ' * 20}{i}\n"
        )
    return structure, indexer


def _damage(indexer: WikiIndexer, kind: str) -> None:
    conn = sqlite3.connect(indexer.db_path)
    try:
        corrupt_fts5_index(conn, "wiki_fts", kind)
    finally:
        conn.close()


@pytest.mark.parametrize("kind", CORRUPTIONS)
async def test_a_damaged_index_is_rebuilt_when_the_indexer_starts(tmp_path: Path, kind: str) -> None:
    structure, indexer = await _filled_indexer(tmp_path / "vault")
    _damage(indexer, kind)

    restarted = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

    assert len(await restarted.search("kelvin", limit=5)) == 5


async def test_search_heals_an_index_the_query_cannot_read(tmp_path: Path) -> None:
    _, indexer = await _filled_indexer(tmp_path / "vault")
    _damage(indexer, "empty-docsize")

    assert len(await indexer.search("kelvin", limit=5)) == 5


async def test_search_returns_nothing_when_the_database_error_is_not_a_damaged_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    indexer = await _indexer_with_one_page(tmp_path / "vault")

    def unreadable(conn: sqlite3.Connection, fts_table: str, columns: str) -> str:
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(fts_search, "_published_match_select", unreadable)

    assert await indexer.search("kelvin") == []


async def test_search_raises_a_programming_error_instead_of_hiding_it_as_no_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A query that binds the wrong number of values is a bug in the code, not a damaged index."""
    indexer = await _indexer_with_one_page(tmp_path / "vault")
    real = fts_search._published_match_select
    monkeypatch.setattr(
        fts_search,
        "_published_match_select",
        lambda conn, fts_table, columns: real(conn, fts_table, columns) + " AND ? IS NOT NULL",
    )

    with pytest.raises(sqlite3.ProgrammingError, match="number of bindings"):
        await indexer.search("kelvin")


_GRADED_PAGES = 31


async def _graded_indexer(root: Path, *, store: AsyncMock | None = None) -> tuple[WikiIndexer, list[tuple[str, float]]]:
    """An index of pages that all match "kelvin", plus the index's own best-first order of them.

    With a ``store`` the indexer runs hybrid search against it.
    """
    structure = WikiStructure(root)
    structure.ensure_structure()
    if store is None:
        indexer = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))
    else:
        store.collection_exists.return_value = False
        embedding = AsyncMock()
        embedding.embed.return_value = [0.1, 0.2, 0.3]
        embedding.embed_batch.side_effect = lambda chunks: [[0.1, 0.2, 0.3] for _ in chunks]
        indexer = WikiIndexer(structure, WikiConfig(enable_hybrid_search=True), vector_store=store, embedding=embedding)
    for i in range(_GRADED_PAGES):
        body = "kelvin " * (_GRADED_PAGES - i) + "plain notes about an unrelated subject " * 4
        await indexer.upsert(f"page-{i:02d}", f"---\ntype: concept\n---\n\n## Compiled Truth\n{body}\n")
    conn = sqlite3.connect(indexer.db_path)
    try:
        ranked = conn.execute(
            "SELECT concept_name, rank FROM wiki_fts WHERE wiki_fts MATCH ? ORDER BY rank",
            (tokenize_for_fts("kelvin"),),
        ).fetchall()
    finally:
        conn.close()
    assert len({rank for _, rank in ranked}) == _GRADED_PAGES, "the fixture needs one distinct rank per page"
    return indexer, ranked


@pytest.mark.parametrize(("limit", "offset"), [(1, 0), (5, 0), (_GRADED_PAGES, 0), (5, 5)])
async def test_search_returns_the_best_match_first(tmp_path: Path, limit: int, offset: int) -> None:
    indexer, ranked = await _graded_indexer(tmp_path / "vault")
    best_first = [name for name, _ in ranked]

    results = await indexer.search("kelvin", limit=limit, offset=offset)

    assert [name for name, _ in results] == best_first[offset : offset + limit]
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


async def test_hybrid_search_keeps_the_fusion_order_of_the_two_rankings(tmp_path: Path) -> None:
    store = AsyncMock()
    indexer, ranked = await _graded_indexer(tmp_path / "vault", store=store)
    text_order = [name for name, _ in ranked][:5]
    vector_order = [text_order[3], text_order[4], text_order[0]]
    store.search.return_value = [
        SearchResult(
            document=VectorDocument(id=name, content="", vector=[], metadata={"concept_name": name}),
            score=1.0 - i * 0.1,
        )
        for i, name in enumerate(vector_order)
    ]

    results = await indexer.search("kelvin", limit=5)

    # Reciprocal rank fusion scores 1 / (60 + position + 1) per ranking, so only the positions decide.
    assert [name for name, _ in results] == [text_order[0], text_order[3], text_order[4], text_order[1], text_order[2]]
