"""Tests for wiki asset indexer."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval import asset_index
from myrm_agent_harness.toolkits.wiki.retrieval.asset_index import WikiAssetIndexer
from tests.support.fts5_corruption import CORRUPTIONS, corrupt_fts5_index
from tests.support.fts5_full_disk import limit_database_growth
from tests.support.fts5_legacy import downgrade_fts5_tokenizer, fts5_declaration, fts5_rows


@pytest.mark.asyncio
async def test_an_old_asset_index_still_opens_when_the_disk_has_no_room_to_convert_it(
    wiki_structure: WikiStructure, assets_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    indexer = await _indexed(wiki_structure, assets_dir, {"model.png": "Transformers trained on large datasets"})
    with closing(sqlite3.connect(indexer.db_path)) as conn:
        conn.executemany(
            "INSERT INTO wiki_assets_fts(filename, caption) VALUES (?, ?)",
            [(f"filler-{i}.png", f"{'Green tea leaves steeped slowly. ' * 30}{i}") for i in range(400)],
        )
        conn.commit()
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS)
    rows = fts5_rows(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS)
    with monkeypatch.context() as full_disk:
        limit_database_growth(full_disk, extra_pages=6, journal_mode="wal")

        crowded = WikiAssetIndexer(wiki_structure, _CONFIG, caption_provider=_StubCaptionProvider({}))

        assert "porter" not in fts5_declaration(indexer.db_path, "wiki_assets_fts")
        assert fts5_rows(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS) == rows
        assert [hit.filename for hit in await crowded.search("transformers")] == ["model.png"]

    reopened = WikiAssetIndexer(wiki_structure, _CONFIG, caption_provider=_StubCaptionProvider({}))

    assert "porter" in fts5_declaration(indexer.db_path, "wiki_assets_fts")
    assert fts5_rows(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS) == rows
    assert [hit.filename for hit in await reopened.search("transformer")] == ["model.png"]


class _StubCaptionProvider:
    def __init__(self, captions: dict[str, str]) -> None:
        self._captions = captions
        self.calls: list[str] = []

    async def caption_file(self, path: Path) -> str:
        self.calls.append(path.name)
        return self._captions.get(path.name, f"Caption for {path.stem}")


@pytest.fixture
def wiki_structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path / "vault")
    structure.ensure_structure()
    return structure


@pytest.fixture
def assets_dir(wiki_structure: WikiStructure) -> Path:
    assets = wiki_structure.wiki_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    return assets


@pytest.mark.asyncio
async def test_asset_index_sha256_skip(wiki_structure: WikiStructure, assets_dir: Path) -> None:
    image = assets_dir / "diagram.png"
    image.write_bytes(b"fake-png-bytes")

    provider = _StubCaptionProvider({})
    config = WikiConfig(enable_asset_index=True, enable_hybrid_search=False)
    indexer = WikiAssetIndexer(wiki_structure, config, caption_provider=provider)

    first = await indexer.index_file(image)
    second = await indexer.index_file(image)

    assert first is True
    assert second is False
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_asset_search_fts(wiki_structure: WikiStructure, assets_dir: Path) -> None:
    image = assets_dir / "payment-flow.png"
    image.write_bytes(b"payment-diagram")

    provider = _StubCaptionProvider({"payment-flow.png": "Checkout payment sequence with gateway"})
    config = WikiConfig(enable_asset_index=True, enable_hybrid_search=False)
    indexer = WikiAssetIndexer(wiki_structure, config, caption_provider=provider)
    await indexer.index_file(image)

    hits = await indexer.search("payment gateway sequence", limit=5)
    assert hits
    assert hits[0].filename == "payment-flow.png"
    assert "Checkout payment" in hits[0].caption


@pytest.mark.asyncio
async def test_scan_image_references(wiki_structure: WikiStructure, assets_dir: Path) -> None:
    concept_path = wiki_structure.concepts_dir / "Payment.md"
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    concept_path.write_text("# Payment\n\n![diagram](payment-flow.png)\n", encoding="utf-8")

    config = WikiConfig(enable_asset_index=True)
    indexer = WikiAssetIndexer(wiki_structure, config, caption_provider=_StubCaptionProvider({}))
    refs = indexer.scan_image_references()

    assert refs["payment-flow.png"] == ["Payment"]


@pytest.mark.asyncio
async def test_purge_orphan_entries(wiki_structure: WikiStructure, assets_dir: Path) -> None:
    image = assets_dir / "removed-diagram.png"
    image.write_bytes(b"orphan-test")

    provider = _StubCaptionProvider({"removed-diagram.png": "Diagram that will be deleted from disk"})
    config = WikiConfig(enable_asset_index=True, enable_hybrid_search=False)
    indexer = WikiAssetIndexer(wiki_structure, config, caption_provider=provider)
    await indexer.index_file(image)

    hits = await indexer.search("deleted diagram", limit=3)
    assert hits

    image.unlink()
    purged = await indexer.purge_orphan_entries()
    assert purged == 1

    hits_after = await indexer.search("deleted diagram", limit=3)
    assert not hits_after


@pytest.mark.asyncio
async def test_asset_recall_gate_meets_baseline(wiki_structure: WikiStructure, assets_dir: Path) -> None:
    """CI anchor: caption FTS must retrieve indexed asset by semantic query."""
    image = assets_dir / "architecture-diagram.png"
    image.write_bytes(b"diagram-bytes")

    provider = _StubCaptionProvider(
        {"architecture-diagram.png": "Microservice architecture diagram with API gateway and payment service"}
    )
    config = WikiConfig(enable_asset_index=True, enable_hybrid_search=False)
    indexer = WikiAssetIndexer(wiki_structure, config, caption_provider=provider)
    await indexer.index_file(image)

    hits = await indexer.search("payment service architecture diagram", limit=3)
    assert hits, "asset recall gate: expected at least one hit"
    assert hits[0].filename == "architecture-diagram.png"


_CONFIG = WikiConfig(enable_asset_index=True, enable_hybrid_search=False)


async def _indexed(structure: WikiStructure, assets: Path, captions: dict[str, str]) -> WikiAssetIndexer:
    for name in captions:
        (assets / name).write_bytes(name.encode())
    indexer = WikiAssetIndexer(structure, _CONFIG, caption_provider=_StubCaptionProvider(captions))
    for name in captions:
        await indexer.index_file(assets / name)
    return indexer


def _damage(indexer: WikiAssetIndexer, kind: str) -> None:
    conn = sqlite3.connect(indexer.db_path)
    try:
        corrupt_fts5_index(conn, "wiki_assets_fts", kind)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_asset_search_returns_the_strongest_matches_first(
    wiki_structure: WikiStructure, assets_dir: Path
) -> None:
    """Captions repeat the query 8, 7, ... 1 times, so the stronger the match the lower the image number."""
    captions = {
        f"img{k}.png": "payment gateway " * (8 - k) + " ".join(f"filler{k}x{i}" for i in range(6 + k)) for k in range(8)
    }
    indexer = await _indexed(wiki_structure, assets_dir, captions)

    hits = await indexer.search("payment gateway", limit=3)

    assert [hit.filename for hit in hits] == ["img0.png", "img1.png", "img2.png"]


def _many_captions() -> dict[str, str]:
    return {f"img{i:02d}.png": f"payment gateway diagram number {i} " * 6 for i in range(40)}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", CORRUPTIONS)
async def test_a_damaged_asset_index_is_rebuilt_when_the_indexer_starts(
    wiki_structure: WikiStructure, assets_dir: Path, kind: str
) -> None:
    captions = _many_captions()
    indexer = await _indexed(wiki_structure, assets_dir, captions)
    _damage(indexer, kind)

    restarted = WikiAssetIndexer(wiki_structure, _CONFIG, caption_provider=_StubCaptionProvider(captions))

    assert len(await restarted.search("payment gateway", limit=5)) == 5


@pytest.mark.asyncio
async def test_asset_search_heals_an_index_the_query_cannot_read(
    wiki_structure: WikiStructure, assets_dir: Path
) -> None:
    indexer = await _indexed(wiki_structure, assets_dir, _many_captions())
    _damage(indexer, "empty-docsize")

    assert len(await indexer.search("payment gateway", limit=5)) == 5


@pytest.mark.asyncio
async def test_asset_search_raises_a_programming_error_instead_of_hiding_it_as_no_results(
    wiki_structure: WikiStructure, assets_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A query that binds the wrong number of values is a bug in the code, not a damaged index."""
    indexer = await _indexed(wiki_structure, assets_dir, {"a.png": "payment gateway"})

    def binds_one_value_too_many(conn: sqlite3.Connection, fts_query: str, limit: int) -> list[tuple[str, float]]:
        conn.execute("SELECT filename FROM wiki_assets_fts WHERE wiki_assets_fts MATCH ?", (fts_query, limit))
        return []

    monkeypatch.setattr(asset_index, "_query_fts", binds_one_value_too_many)

    with pytest.raises(sqlite3.ProgrammingError, match="number of bindings"):
        await indexer.search("payment gateway")


_ASSET_COLUMNS = ("filename", "caption")


@pytest.mark.asyncio
async def test_asset_search_finds_a_caption_under_another_form_of_the_word(
    wiki_structure: WikiStructure, assets_dir: Path
) -> None:
    indexer = await _indexed(wiki_structure, assets_dir, {"model.png": "Transformers trained on large datasets"})

    assert [hit.filename for hit in await indexer.search("transformer training dataset")] == ["model.png"]


@pytest.mark.asyncio
async def test_an_asset_index_without_stemming_is_converted_without_captioning_again(
    wiki_structure: WikiStructure, assets_dir: Path
) -> None:
    indexer = await _indexed(
        wiki_structure,
        assets_dir,
        {"model.png": "Transformers trained on large datasets", "tea.png": "Green tea leaves"},
    )
    downgrade_fts5_tokenizer(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS)
    rows = fts5_rows(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS)
    assert await indexer.search("transformer") == [], "an index without stemming misses another form of the word"
    provider = _StubCaptionProvider({})

    reopened = WikiAssetIndexer(wiki_structure, _CONFIG, caption_provider=provider)

    assert "porter" in fts5_declaration(indexer.db_path, "wiki_assets_fts")
    assert fts5_rows(indexer.db_path, "wiki_assets_fts", _ASSET_COLUMNS) == rows
    assert [hit.filename for hit in await reopened.search("transformer")] == ["model.png"]
    assert await reopened.index_file(assets_dir / "model.png") is False
    assert provider.calls == [], "converting the index must not call the vision model again"
