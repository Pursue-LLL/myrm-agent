"""FAQ interceptor assembly: the embedding backend comes from WebUI retrieval settings, never env vars.

The regression these hold down: the factory used to read ``EMBEDDING_*`` env vars, which production
never sets, so ``get_faq_interceptor()`` silently returned None and every FAQ corpus was dead.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

import app.services.faq.factory as faq_factory


@pytest.fixture(autouse=True)
def _clean_singleton() -> None:
    faq_factory.reset_faq_interceptor()
    yield
    faq_factory.reset_faq_interceptor()


def _stub_embedding_service() -> MagicMock:
    return MagicMock(name="embedding_service")


@pytest.mark.asyncio
async def test_returns_none_when_webui_embedding_is_not_configured() -> None:
    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch(
            "app.core.retriever.vector.defaults.create_default_vector_store",
            new=AsyncMock(return_value=MagicMock()),
        ),
    ):
        assert await faq_factory.get_faq_interceptor() is None


@pytest.mark.asyncio
async def test_builds_interceptor_from_webui_embedding_config() -> None:
    embedding_config = EmbeddingConfig(
        model="BAAI/bge-m3",
        api_key="sk-from-webui",
        api_base="https://api.siliconflow.cn/v1",
    )
    service = _stub_embedding_service()
    vector_store = MagicMock(name="vector_store")

    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(return_value=(embedding_config, None)),
        ),
        patch(
            "myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service",
            return_value=service,
        ) as get_service,
        patch(
            "app.core.retriever.vector.defaults.create_default_vector_store",
            new=AsyncMock(return_value=vector_store),
        ),
    ):
        interceptor = await faq_factory.get_faq_interceptor()

    assert interceptor is not None
    get_service.assert_called_once_with(embedding_config)


@pytest.mark.asyncio
async def test_caches_one_interceptor_until_reset() -> None:
    embedding_config = EmbeddingConfig(model="BAAI/bge-m3", api_key="sk-from-webui")
    load_configs = AsyncMock(return_value=(embedding_config, None))

    with (
        patch("app.services.agent.platform_config.load_platform_retrieval_configs", new=load_configs),
        patch(
            "myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service",
            return_value=_stub_embedding_service(),
        ),
        patch(
            "app.core.retriever.vector.defaults.create_default_vector_store",
            new=AsyncMock(return_value=MagicMock()),
        ),
    ):
        first = await faq_factory.get_faq_interceptor()
        second = await faq_factory.get_faq_interceptor()
        assert first is second
        assert load_configs.await_count == 1

        faq_factory.reset_faq_interceptor()
        third = await faq_factory.get_faq_interceptor()

    assert third is not first
    assert load_configs.await_count == 2


@pytest.mark.asyncio
async def test_unreadable_config_degrades_to_none_instead_of_failing_the_turn() -> None:
    with patch(
        "app.services.agent.platform_config.load_platform_retrieval_configs",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        assert await faq_factory.get_faq_interceptor() is None
