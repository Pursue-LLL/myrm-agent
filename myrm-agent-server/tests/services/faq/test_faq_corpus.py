"""Unit tests for FAQ corpus CRUD and bulk import."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models.faq import FaqCorpus, FaqEntry
from app.services.faq.corpus import FaqCorpusService


def _make_corpus(agent_id: str = "agent-1", **kw: object) -> FaqCorpus:
    defaults = dict(
        id="corpus-1",
        agent_id=agent_id,
        enabled=True,
        threshold=0.85,
        min_score_gap=0.15,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kw)
    c = MagicMock(spec=FaqCorpus)
    for k, v in defaults.items():
        setattr(c, k, v)
    c.entries = []
    return c


def _make_entry(entry_id: str = "e-1", corpus_id: str = "corpus-1", **kw: object) -> FaqEntry:
    defaults = dict(
        id=entry_id,
        corpus_id=corpus_id,
        question="How to reset password?",
        answer="Go to Settings > Security > Reset Password.",
        tags="security,password",
        sort_order=0,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kw)
    e = MagicMock(spec=FaqEntry)
    for k, v in defaults.items():
        setattr(e, k, v)
    return e


@asynccontextmanager
async def _mock_session(session: AsyncMock):
    yield session


@pytest.fixture
def mock_session():
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock
    return session


@pytest.fixture
def service():
    return FaqCorpusService()


@pytest.mark.asyncio
async def test_get_or_create_corpus_creates_new(service: FaqCorpusService, mock_session: AsyncMock) -> None:
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    corpus_created = _make_corpus()
    mock_session.refresh = AsyncMock(return_value=None)

    original_add = mock_session.add

    def capture_add(obj: object) -> None:
        for attr in ("id", "agent_id", "enabled", "threshold", "min_score_gap"):
            if hasattr(obj, attr) and hasattr(corpus_created, attr):
                pass
        original_add(obj)

    mock_session.add = capture_add

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(mock_session)):
        await service.get_or_create_corpus("agent-1", db=mock_session)

    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_corpus_returns_existing(service: FaqCorpusService, mock_session: AsyncMock) -> None:
    existing = _make_corpus()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = result_mock

    result = await service.get_or_create_corpus("agent-1", db=mock_session)
    assert result == existing
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_list_entries_returns_ordered(service: FaqCorpusService) -> None:
    entries = [_make_entry("e-1"), _make_entry("e-2")]
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = entries
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        result = await service.list_entries("agent-1")

    assert len(result) == 2
    assert result[0].id == "e-1"


@pytest.mark.asyncio
async def test_add_entry_creates_and_commits(service: FaqCorpusService) -> None:
    corpus = _make_corpus()
    session = AsyncMock()

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = corpus
    session.execute.return_value = get_result

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        await service.add_entry("agent-1", "  How to login?  ", "  Click Login.  ", tags=" auth ")

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_entry_partial_update(service: FaqCorpusService) -> None:
    entry = _make_entry()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = entry
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        result = await service.update_entry("e-1", question="New question?")

    assert result is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_entry_not_found(service: FaqCorpusService) -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        result = await service.update_entry("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_delete_entry_returns_true(service: FaqCorpusService) -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.rowcount = 1
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        assert await service.delete_entry("e-1") is True


@pytest.mark.asyncio
async def test_delete_entry_returns_false(service: FaqCorpusService) -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.rowcount = 0
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        assert await service.delete_entry("nonexistent") is False


@pytest.mark.asyncio
async def test_update_corpus_settings_clamps_values(service: FaqCorpusService) -> None:
    corpus = _make_corpus()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = corpus
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        await service.update_corpus_settings(
            "agent-1", threshold=0.5, min_score_gap=1.0,
        )

    assert corpus.threshold == 0.75
    assert corpus.min_score_gap == 0.5


@pytest.mark.asyncio
async def test_bulk_import_single_session(service: FaqCorpusService) -> None:
    corpus = _make_corpus()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = corpus
    session.execute.return_value = result_mock

    items = [
        {"question": "Q1", "answer": "A1"},
        {"question": "Q2", "answer": "A2", "tags": "t1"},
        {"question": "", "answer": "A3"},
        {"question": "Q4", "answer": ""},
    ]

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        count = await service.bulk_import("agent-1", items)

    assert count == 2
    assert session.add.call_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_import_empty_items(service: FaqCorpusService) -> None:
    count = await service.bulk_import("agent-1", [])
    assert count == 0


@pytest.mark.asyncio
async def test_bulk_import_all_invalid(service: FaqCorpusService) -> None:
    items = [{"question": "", "answer": ""}, {"question": " ", "answer": "  "}]
    count = await service.bulk_import("agent-1", items)
    assert count == 0


@pytest.mark.asyncio
async def test_rebuild_index_empty_corpus(service: FaqCorpusService) -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock

    embedding = AsyncMock()
    vector = AsyncMock()

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        count = await service.rebuild_index("agent-1", embedding, vector)

    assert count == 0
    vector.delete_collection.assert_not_called()


@pytest.mark.asyncio
async def test_rebuild_index_with_entries(service: FaqCorpusService) -> None:
    entries = [_make_entry("e-1"), _make_entry("e-2", question="How to logout?")]
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = entries
    session.execute.return_value = result_mock

    embedding = AsyncMock()
    embedding.dimension = 768
    embedding.embed_batch.return_value = [[0.1] * 768, [0.2] * 768]

    vector = AsyncMock()
    vector.delete_collection.return_value = None

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        count = await service.rebuild_index("agent-1", embedding, vector)

    assert count == 2
    vector.delete_collection.assert_awaited_once_with("faq_agent-1")
    vector.create_collection.assert_awaited_once_with("faq_agent-1", dimension=768)
    vector.upsert.assert_awaited_once()
    docs = vector.upsert.call_args[0][1]
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_rebuild_index_delete_collection_fails_continues(service: FaqCorpusService) -> None:
    entries = [_make_entry("e-1")]
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = entries
    session.execute.return_value = result_mock

    embedding = AsyncMock()
    embedding.dimension = 384
    embedding.embed_batch.return_value = [[0.5] * 384]

    vector = AsyncMock()
    vector.delete_collection.side_effect = RuntimeError("collection not found")

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        count = await service.rebuild_index("agent-1", embedding, vector)

    assert count == 1
    vector.create_collection.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_corpus_settings_toggle_enabled(service: FaqCorpusService) -> None:
    corpus = _make_corpus(enabled=True)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = corpus
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        await service.update_corpus_settings("agent-1", enabled=False)

    assert corpus.enabled is False


@pytest.mark.asyncio
async def test_update_corpus_settings_no_change(service: FaqCorpusService) -> None:
    corpus = _make_corpus(threshold=0.85, min_score_gap=0.15)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = corpus
    session.execute.return_value = result_mock

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        await service.update_corpus_settings("agent-1")

    assert corpus.threshold == 0.85
    assert corpus.min_score_gap == 0.15


@pytest.mark.asyncio
async def test_bulk_import_missing_keys_in_dict(service: FaqCorpusService) -> None:
    """Dicts missing 'question' or 'answer' keys entirely are safely skipped."""
    corpus = _make_corpus()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = corpus
    session.execute.return_value = result_mock

    items: list[dict[str, str]] = [
        {"answer": "orphan answer"},
        {"question": "orphan question"},
        {"question": "valid Q", "answer": "valid A"},
    ]

    with patch("app.services.faq.corpus.get_session", return_value=_mock_session(session)):
        count = await service.bulk_import("agent-1", items)

    assert count == 1
    session.add.assert_called_once()


def test_collection_name_format() -> None:
    from app.services.faq.corpus import _collection_name

    assert _collection_name("agent-123") == "faq_agent-123"
    assert _collection_name("") == "faq_"
