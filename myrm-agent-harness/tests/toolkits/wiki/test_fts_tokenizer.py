"""Wiki search stems English words, and an index written without stemming is converted when it is opened."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval import indexer as indexer_module
from myrm_agent_harness.toolkits.wiki.retrieval.fts_search import WIKI_FTS_COLUMNS
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer
from myrm_agent_harness.utils.db.fts5 import fts5_swap_tokenizer
from tests.support.fts5_corruption import CORRUPTIONS, corrupt_fts5_index
from tests.support.fts5_full_disk import limit_database_growth
from tests.support.fts5_legacy import downgrade_fts5_tokenizer, fts5_declaration, fts5_rows


def _page(body: str) -> str:
    return f"---\ntype: concept\n---\n\n## Compiled Truth\n{body}\n"


def _open(root: Path, *, public: Path | None = None) -> tuple[WikiStructure, WikiIndexer]:
    structure = WikiStructure(root, public_dirs=[public] if public else [])
    structure.ensure_structure()
    return structure, WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))


async def _names(indexer: WikiIndexer, query: str, *, limit: int = 5) -> list[str]:
    return [name for name, _ in await indexer.search(query, limit=limit)]


async def _vault(root: Path) -> tuple[WikiStructure, WikiIndexer]:
    """One compiled page, one directory sidecar and one raw-text entry: the three kinds of row wiki_fts holds."""
    structure, indexer = _open(root)
    await indexer.upsert("attention", _page("Transformers are trained on large datasets."))
    await indexer.upsert("kitchen", _page("Whisk the eggs and fold in the flour."))
    await indexer.upsert_sidecar("ml", level=0, content="Notes about trained transformers")
    indexer.index_raw_text("uncompiled-note", "zebrafinches are small songbirds")
    return structure, indexer


def _record_swaps(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """What every tokenizer swap an indexer starts up with returned."""
    outcomes: list[bool] = []

    def recording(conn: sqlite3.Connection, table: str, columns: tuple[str, ...], tokenizer: str) -> bool:
        swapped = fts5_swap_tokenizer(conn, table, columns, tokenizer)
        outcomes.append(swapped)
        return swapped

    monkeypatch.setattr(indexer_module, "fts5_swap_tokenizer", recording)
    return outcomes


@pytest.mark.parametrize("query", ["transformer", "training", "dataset", "train transformers"])
async def test_a_query_finds_a_page_that_uses_another_form_of_the_word(tmp_path: Path, query: str) -> None:
    _, indexer = await _vault(tmp_path / "vault")

    assert await _names(indexer, query) == ["attention"]


async def test_a_query_finds_a_raw_text_entry_under_another_form_of_the_word(tmp_path: Path) -> None:
    _, indexer = await _vault(tmp_path / "vault")

    assert await _names(indexer, "zebrafinch") == ["raw:uncompiled-note"]


async def test_a_query_finds_a_directory_sidecar_under_another_form_of_the_word(tmp_path: Path) -> None:
    _, indexer = await _vault(tmp_path / "vault")

    assert [(path, level) for path, level, _ in await indexer.search_sidecars("transformer")] == [("ml", 0)]


async def test_an_index_without_stemming_is_converted_when_opened_and_keeps_every_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    structure, indexer = await _vault(tmp_path / "vault")
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    rows = fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    assert {"attention", "raw:uncompiled-note"} <= {str(row[1]) for row in rows}
    assert await _names(indexer, "transformer") == [], "an index without stemming misses another form of the word"
    swaps = _record_swaps(monkeypatch)

    reopened = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

    assert swaps == [True]
    assert "porter" in fts5_declaration(indexer.db_path, "wiki_fts")
    assert fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS) == rows
    assert await _names(reopened, "transformer") == ["attention"]
    assert await _names(reopened, "zebrafinch") == ["raw:uncompiled-note"]
    assert [(path, level) for path, level, _ in await reopened.search_sidecars("transformer")] == [("ml", 0)]

    WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

    assert swaps == [True, False], "an index that already stems is not converted again"
    assert fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS) == rows


@pytest.mark.parametrize("kind", CORRUPTIONS)
async def test_a_damaged_index_without_stemming_is_converted_when_opened(tmp_path: Path, kind: str) -> None:
    structure, indexer = _open(tmp_path / "vault")
    for i in range(40):
        await indexer.upsert(f"page-{i:02d}", _page(f"{'Transformers are trained on kelvin notes. ' * 20}{i}"))
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    with closing(sqlite3.connect(indexer.db_path)) as conn:
        corrupt_fts5_index(conn, "wiki_fts", kind)

    reopened = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

    assert "porter" in fts5_declaration(indexer.db_path, "wiki_fts")
    assert len(await _names(reopened, "transformer", limit=40)) == 40


async def test_two_indexers_opening_the_same_old_index_at_once_convert_it_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    structure, indexer = await _vault(tmp_path / "vault")
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    rows = fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    swaps = _record_swaps(monkeypatch)
    start = threading.Barrier(2)

    def open_indexer() -> WikiIndexer:
        start.wait()
        return WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

    first, second = await asyncio.gather(asyncio.to_thread(open_indexer), asyncio.to_thread(open_indexer))

    assert sorted(swaps) == [False, True]
    assert fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS) == rows
    assert await _names(first, "transformer") == await _names(second, "transformer") == ["attention"]


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
async def test_an_old_index_still_opens_when_the_disk_has_no_room_to_convert_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal_mode: str
) -> None:
    structure, indexer = _open(tmp_path / "vault")
    for i in range(60):
        await indexer.upsert(f"page-{i:02d}", _page(f"{'Transformers are trained on kelvin notes. ' * 30}{i}"))
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    rows = fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    swaps = _record_swaps(monkeypatch)
    with monkeypatch.context() as full_disk:
        limit_database_growth(full_disk, extra_pages=6, journal_mode=journal_mode)

        crowded = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

        assert swaps == [False]
        assert "porter" not in fts5_declaration(indexer.db_path, "wiki_fts")
        assert fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS) == rows
        assert len(await _names(crowded, "transformers", limit=60)) == 60

    reopened = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))

    assert swaps == [False, True]
    assert fts5_rows(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS) == rows
    assert len(await _names(reopened, "transformer", limit=60)) == 60


async def test_a_shared_index_without_stemming_is_searched_along_with_the_stemmed_local_index(tmp_path: Path) -> None:
    _, shared = _open(tmp_path / "shared")
    await shared.upsert("embeddings", _page("A transformer turns text into vectors."))
    downgrade_fts5_tokenizer(shared.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    _, local = _open(tmp_path / "local", public=tmp_path / "shared")
    await local.upsert("attention", _page("Transformers are trained on large datasets."))

    assert sorted(await _names(local, "transformer")) == ["attention", "embeddings"]
    assert "porter" not in fts5_declaration(shared.db_path, "wiki_fts"), "a reader never alters a shared index"


async def test_chinese_queries_match_the_same_pages_with_and_without_stemming(tmp_path: Path) -> None:
    structure, indexer = _open(tmp_path / "vault")
    await indexer.upsert("graph", _page("知识图谱构建方法与实体抽取。"))
    await indexer.upsert("kitchen", _page("Whisk the eggs and fold in the flour."))
    queries = ["知识图谱", "实体抽取", "构建方法"]

    stemmed = {query: await _names(indexer, query) for query in queries}
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_fts", WIKI_FTS_COLUMNS)
    unstemmed = {query: await _names(indexer, query) for query in queries}
    converted = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))
    reconverted = {query: await _names(converted, query) for query in queries}

    assert stemmed == unstemmed == reconverted == {query: ["graph"] for query in queries}
