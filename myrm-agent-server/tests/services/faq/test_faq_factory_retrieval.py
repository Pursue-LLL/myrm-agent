"""FAQ interceptor assembly: the embedding backend comes from WebUI retrieval settings, never env vars.

What these hold down: the factory reads the embedding saved in Settings, not ``EMBEDDING_*`` env vars (production
never sets them, so ``get_faq_interceptor()`` would return None and every FAQ corpus would be dead); and it follows an
embedding model saved while the process runs, instead of embedding FAQ lookups with the one the first interceptor was
built for.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

import app.services.faq.factory as faq_factory

BGE_M3 = EmbeddingConfig(model="BAAI/bge-m3", api_key="sk-from-webui", api_base="https://api.siliconflow.cn/v1")


@contextmanager
def _faq_dependencies(*answers: EmbeddingConfig | None | Exception) -> Iterator[tuple[MagicMock, AsyncMock]]:
    """Settings that answer with each of ``answers`` in turn; yields the embedding-service and vector-store factories."""
    load_configs = AsyncMock(side_effect=[answer if isinstance(answer, Exception) else (answer, None) for answer in answers])
    get_service = MagicMock(side_effect=lambda config: MagicMock(name=f"embedding_service_{config.model}"))
    create_store = AsyncMock(return_value=MagicMock(name="vector_store"))
    with (
        patch("app.services.agent.platform_config.load_platform_retrieval_configs", new=load_configs),
        patch("myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service", new=get_service),
        patch("app.core.retriever.vector.defaults.create_default_vector_store", new=create_store),
    ):
        yield get_service, create_store


@pytest.fixture(autouse=True)
async def _no_interceptor_cached() -> None:
    """An unconfigured embedding drops whatever interceptor an earlier test left cached."""
    with _faq_dependencies(None):
        await faq_factory.get_faq_interceptor()


async def test_returns_none_when_webui_embedding_is_not_configured() -> None:
    with _faq_dependencies(None):
        assert await faq_factory.get_faq_interceptor() is None


async def test_builds_interceptor_from_webui_embedding_config() -> None:
    with _faq_dependencies(BGE_M3) as (get_service, create_store):
        interceptor = await faq_factory.get_faq_interceptor()

    assert interceptor is not None
    get_service.assert_called_once_with(BGE_M3)
    create_store.assert_awaited_once()


async def test_reuses_one_interceptor_and_one_vector_store_while_the_embedding_config_is_unchanged() -> None:
    """A remote Qdrant store is a new client per creation, so an unchanged config must not build another one."""
    with _faq_dependencies(BGE_M3, BGE_M3, BGE_M3) as (get_service, create_store):
        first = await faq_factory.get_faq_interceptor()
        second = await faq_factory.get_faq_interceptor()
        third = await faq_factory.get_faq_interceptor()

    assert first is not None
    assert first is second is third
    get_service.assert_called_once()
    create_store.assert_awaited_once()


@pytest.mark.parametrize(
    "saved",
    [
        EmbeddingConfig(model="BAAI/bge-large-zh", api_key="sk-from-webui", api_base="https://api.siliconflow.cn/v1"),
        EmbeddingConfig(model="BAAI/bge-m3", api_key="sk-rotated", api_base="https://api.siliconflow.cn/v1"),
        EmbeddingConfig(model="BAAI/bge-m3", api_key="sk-from-webui", api_base="https://embeddings.example.test/v1"),
    ],
    ids=["model", "api_key", "api_base"],
)
async def test_rebuilds_the_interceptor_when_the_saved_embedding_config_changes(saved: EmbeddingConfig) -> None:
    with _faq_dependencies(BGE_M3, saved) as (get_service, _):
        before = await faq_factory.get_faq_interceptor()
        after = await faq_factory.get_faq_interceptor()

    assert before is not None
    assert after is not None
    assert after is not before
    assert get_service.call_args_list[-1].args == (saved,)


async def test_unconfiguring_embedding_drops_the_interceptor() -> None:
    with _faq_dependencies(BGE_M3, None, BGE_M3):
        first = await faq_factory.get_faq_interceptor()
        unconfigured = await faq_factory.get_faq_interceptor()
        configured_again = await faq_factory.get_faq_interceptor()

    assert unconfigured is None
    assert configured_again is not None
    assert configured_again is not first


async def test_a_failed_config_read_does_not_cost_the_interceptor() -> None:
    with _faq_dependencies(BGE_M3, RuntimeError("db down"), BGE_M3) as (get_service, _):
        first = await faq_factory.get_faq_interceptor()
        failed = await faq_factory.get_faq_interceptor()
        recovered = await faq_factory.get_faq_interceptor()

    assert first is not None
    assert failed is None
    assert recovered is first
    get_service.assert_called_once()


async def test_unreadable_config_degrades_to_none_instead_of_failing_the_turn() -> None:
    with _faq_dependencies(RuntimeError("db down")):
        assert await faq_factory.get_faq_interceptor() is None
