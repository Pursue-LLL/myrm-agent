"""FAQ index rebuild against the real embedding client: what a rebuild may touch, and when.

The embedding client is the product's own CloudEmbedding talking to a loopback provider, so a model whose vector size is
only learned from its first answer and a provider that refuses the call behave as they do in production. The vector
store is a mock: the assertions are about which of its calls a rebuild makes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from myrm_agent_harness.toolkits.llms.transport import LLMCallError
from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig, get_embedding_service

from app.database.models.faq import FaqEntry
from app.services.faq.corpus import FaqCorpusService
from tests.support.fake_retrieval_provider import FakeRetrievalProvider, fake_retrieval_provider

# The client knows the vector size of a preset model up front and learns that of any other from its first answer.
_PRESET_MODEL = "openai/text-embedding-3-small"
_UNPRESET_MODEL = "openai/faq-test-embed"


def _entry(entry_id: str, question: str) -> FaqEntry:
    entry = MagicMock(spec=FaqEntry)
    entry.id = entry_id
    entry.question = question
    entry.created_at = datetime.now(tz=timezone.utc)
    return entry


@asynccontextmanager
async def _session_listing(entries: list[FaqEntry]):
    result = MagicMock()
    result.scalars.return_value.all.return_value = entries
    session = AsyncMock()
    session.execute.return_value = result
    yield session


@pytest.fixture
def provider() -> Iterator[FakeRetrievalProvider]:
    with fake_retrieval_provider() as running:
        yield running


def _service_for(provider: FakeRetrievalProvider, model: str) -> EmbeddingService:
    # One service per (model, key, base): a fresh key keeps every test on its own, undetected, dimension.
    config = EmbeddingConfig(model=model, api_key=f"sk-faq-{uuid4().hex}", api_base=provider.api_base)
    return get_embedding_service(config)


async def _rebuild(embedding: EmbeddingService, vector: AsyncMock) -> int:
    entries = [_entry("e-1", "How to reset password?"), _entry("e-2", "How to log out?")]
    with patch("app.services.faq.corpus.get_session", return_value=_session_listing(entries)):
        return await FaqCorpusService().rebuild_index("agent-1", embedding, vector)


@pytest.mark.asyncio
async def test_a_model_whose_vector_size_is_learned_from_its_first_answer_builds_the_index(
    provider: FakeRetrievalProvider,
) -> None:
    provider.dimension = 6
    vector = AsyncMock()

    count = await _rebuild(_service_for(provider, _UNPRESET_MODEL), vector)

    assert count == 2
    vector.create_collection.assert_awaited_once_with("faq_agent-1", dimension=6)
    [docs] = [call.args[1] for call in vector.upsert.await_args_list]
    assert [len(doc.vector) for doc in docs] == [6, 6]


@pytest.mark.asyncio
async def test_a_refused_embedding_call_leaves_the_serving_index_untouched(provider: FakeRetrievalProvider) -> None:
    provider.status = 401
    vector = AsyncMock()

    with pytest.raises(LLMCallError):
        await _rebuild(_service_for(provider, _PRESET_MODEL), vector)

    vector.delete_collection.assert_not_called()
    vector.create_collection.assert_not_called()
    vector.upsert.assert_not_called()
