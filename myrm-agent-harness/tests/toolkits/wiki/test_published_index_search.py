"""The publish gate runs inside the index query, so drafts never crowd published pages out of a result page,
an index that was created but never filled is told apart from a query that matched nothing, and an index in a
read-only directory is still searchable."""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval import fts_search
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

_DRAFT_BODY = "kelvin " * 12
_FILLER = "plain notes about an unrelated subject " * 4


def _page(status: str | None, body: str) -> str:
    status_line = f"publish_status: {status}\n" if status else ""
    return f"---\ntype: concept\n{status_line}---\n\n## Compiled Truth\n{body}\n"


def _published_body(rank: int) -> str:
    """Fewer mentions rank lower, so every published page has its own place in the order."""
    return f"{'kelvin ' * (8 - rank)}{_FILLER}"


def _new_indexer(root: Path, *, public_dirs: list[Path] | None = None) -> WikiIndexer:
    structure = WikiStructure(root, public_dirs=public_dirs or [])
    structure.ensure_structure()
    return WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))


async def _fill(indexer: WikiIndexer, *, drafts: int, published: int, blocked: int = 0) -> None:
    for i in range(drafts):
        await indexer.upsert(f"draft-{i}", _page("draft", _DRAFT_BODY))
    for i in range(blocked):
        await indexer.upsert(f"blocked-{i}", _page("blocked", _DRAFT_BODY))
    for i in range(published):
        await indexer.upsert(f"public-{i}", _page(None, _published_body(i)))


def _add_sidecar_row(db_path: Path, name: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content, search_terms) VALUES (?, ?, ?)",
                (name, _DRAFT_BODY, _DRAFT_BODY),
            )
    finally:
        conn.close()


@pytest.fixture
def indexer(tmp_path: Path) -> WikiIndexer:
    return _new_indexer(tmp_path / "vault")


@pytest.fixture
def read_only_dir() -> Iterator[Callable[[Path], None]]:
    """Make a directory read-only for the test and restore it afterwards so ``tmp_path`` can be cleaned up."""
    locked: list[Path] = []

    def lock(directory: Path) -> None:
        directory.chmod(0o555)
        locked.append(directory)

    yield lock
    for directory in locked:
        directory.chmod(0o755)


async def test_drafts_never_crowd_published_pages_out_of_a_search_page(indexer: WikiIndexer) -> None:
    await _fill(indexer, drafts=12, published=3)

    names = {name for name, _ in await indexer.search("kelvin", limit=5)}

    assert names == {"public-0", "public-1", "public-2"}


async def test_blocked_pages_are_gated_as_drafts_are(indexer: WikiIndexer) -> None:
    await _fill(indexer, drafts=4, blocked=4, published=2)

    names = {name for name, _ in await indexer.search("kelvin", limit=3)}

    assert names == {"public-0", "public-1"}


async def test_an_offset_counts_published_pages_only(indexer: WikiIndexer) -> None:
    await _fill(indexer, drafts=10, published=6)

    first_page = await indexer.search("kelvin", limit=4, offset=0)
    last_page = await indexer.search("kelvin", limit=4, offset=4)

    assert len(first_page) == 4
    assert len(last_page) == 2


async def test_a_page_that_returns_to_published_is_found_again(indexer: WikiIndexer) -> None:
    await indexer.upsert("page", _page("draft", _DRAFT_BODY))
    assert await indexer.search("kelvin") == []

    await indexer.upsert("page", _page(None, _published_body(0)))

    assert [name for name, _ in await indexer.search("kelvin")] == ["page"]


async def test_drafts_of_a_public_vault_do_not_crowd_out_its_published_pages(tmp_path: Path) -> None:
    public = _new_indexer(tmp_path / "public")
    await _fill(public, drafts=12, published=2)
    local = _new_indexer(tmp_path / "local", public_dirs=[tmp_path / "public"])

    names = {name for name, _ in await local.search("kelvin", limit=5)}

    assert names == {"public-0", "public-1"}


async def test_a_public_index_without_publish_metadata_reads_as_published(tmp_path: Path) -> None:
    public = _new_indexer(tmp_path / "public")
    await _fill(public, drafts=0, published=2)
    conn = sqlite3.connect(public.db_path)
    try:
        with conn:
            conn.execute("DROP TABLE wiki_index_meta")
    finally:
        conn.close()
    local = _new_indexer(tmp_path / "local", public_dirs=[tmp_path / "public"])

    names = {name for name, _ in await local.search("kelvin", limit=5)}

    assert names == {"public-0", "public-1"}


async def test_the_read_only_search_ranks_published_pages_before_it_applies_the_limit(indexer: WikiIndexer) -> None:
    await _fill(indexer, drafts=8, blocked=2, published=3)
    _add_sidecar_row(indexer.db_path, "__sidecar__:L0:docs")

    hits = fts_search.search_published_index(indexer.db_path, '"kelvin"', limit=3)

    assert sorted(name for name, _ in hits) == ["public-0", "public-1", "public-2"]
    assert all("kelvin" in truth for _, truth in hits)


async def test_the_read_only_search_never_writes_to_the_index(indexer: WikiIndexer) -> None:
    await _fill(indexer, drafts=2, published=2)
    before = indexer.db_path.read_bytes()

    fts_search.search_published_index(indexer.db_path, '"kelvin"', limit=5)

    assert indexer.db_path.read_bytes() == before


def test_the_read_only_search_reads_an_index_that_predates_publish_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / ".wiki_index.db"
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("CREATE VIRTUAL TABLE wiki_fts USING fts5(concept_name, truth_content)")
            conn.execute("INSERT INTO wiki_fts VALUES ('legacy', 'kelvin scale')")
    finally:
        conn.close()
    before = db_path.read_bytes()

    hits = fts_search.search_published_index(db_path, '"kelvin"', limit=5)

    assert hits == [("legacy", "kelvin scale")]
    assert db_path.read_bytes() == before


def test_the_read_only_search_raises_for_a_missing_index_instead_of_creating_one(tmp_path: Path) -> None:
    db_path = tmp_path / ".wiki_index.db"

    with pytest.raises(sqlite3.OperationalError):
        fts_search.search_published_index(db_path, '"kelvin"', limit=5)

    assert not db_path.exists()


def test_an_index_that_was_created_but_never_filled_has_no_pages(indexer: WikiIndexer) -> None:
    assert fts_search.search_published_index(indexer.db_path, '"kelvin"', limit=5) == []

    assert fts_search.index_has_pages(indexer.db_path) is False


@pytest.mark.parametrize("status", [None, "draft", "blocked"])
async def test_an_index_with_a_page_has_pages_whatever_its_publish_status(
    indexer: WikiIndexer, status: str | None
) -> None:
    await indexer.upsert("page", _page(status, _published_body(0)))
    before = indexer.db_path.read_bytes()

    assert fts_search.index_has_pages(indexer.db_path) is True
    assert indexer.db_path.read_bytes() == before


def test_sidecar_rows_alone_are_not_pages(indexer: WikiIndexer) -> None:
    _add_sidecar_row(indexer.db_path, "__sidecar__:L0:docs")

    assert fts_search.index_has_pages(indexer.db_path) is False


def test_an_index_that_predates_publish_metadata_has_pages(tmp_path: Path) -> None:
    db_path = tmp_path / ".wiki_index.db"
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("CREATE VIRTUAL TABLE wiki_fts USING fts5(concept_name, truth_content)")
            conn.execute("INSERT INTO wiki_fts VALUES ('legacy', 'kelvin scale')")
    finally:
        conn.close()

    assert fts_search.index_has_pages(db_path) is True


def test_has_pages_raises_for_a_missing_index_instead_of_creating_one(tmp_path: Path) -> None:
    db_path = tmp_path / ".wiki_index.db"

    with pytest.raises(sqlite3.OperationalError):
        fts_search.index_has_pages(db_path)

    assert not db_path.exists()


def test_an_index_with_only_raw_uploads_has_no_pages(indexer: WikiIndexer) -> None:
    indexer.index_raw_text("upload", "kelvin notes waiting to be compiled")

    assert fts_search.index_has_pages(indexer.db_path) is False


async def test_a_compiled_page_next_to_raw_uploads_is_a_page(indexer: WikiIndexer) -> None:
    indexer.index_raw_text("upload", "kelvin notes waiting to be compiled")
    await indexer.upsert("page", _page(None, _published_body(0)))

    assert fts_search.index_has_pages(indexer.db_path) is True


def test_rows_still_in_the_wal_file_are_read_from_a_writable_directory(tmp_path: Path) -> None:
    db_path = tmp_path / ".wiki_index.db"
    writer = sqlite3.connect(db_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        fts_search.create_wiki_fts_table(writer)
        with writer:
            writer.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content, search_terms) VALUES ('wal-page', 'kelvin scale', 'kelvin')"
            )

        assert fts_search.search_published_index(db_path, '"kelvin"', limit=5) == [("wal-page", "kelvin scale")]
        assert fts_search.index_has_pages(db_path) is True
    finally:
        writer.close()


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="directory permissions do not restrict this user",
)
async def test_a_wal_index_in_a_read_only_directory_is_searchable(
    indexer: WikiIndexer, read_only_dir: Callable[[Path], None]
) -> None:
    await indexer.upsert("page", _page(None, _published_body(0)))
    assert not Path(f"{indexer.db_path}-wal").exists()
    read_only_dir(indexer.db_path.parent)

    hits = fts_search.search_published_index(indexer.db_path, '"kelvin"', limit=5)

    assert [name for name, _ in hits] == ["page"]
    assert fts_search.index_has_pages(indexer.db_path) is True
