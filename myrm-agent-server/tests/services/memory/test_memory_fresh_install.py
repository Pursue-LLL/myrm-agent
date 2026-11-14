"""A fresh install (no LLM provider, no embedding) still serves the memory surface in keyword mode.

[INPUT]
app.services.agent.platform_config::load_platform_retrieval_configs (POS: WebUI retrieval settings; both models optional)
app.services.memory.extract_retry.resolve_chat_extraction_llm (POS: platform lite / import extraction model resolvers)
app.services.memory.manager_deps::get_memory_manager (POS: memory HTTP dependency; deliberately NOT overridden here)

[OUTPUT]
That reading retrieval settings and resolving memory LLMs never depend on a configured LLM provider, that an
unreadable (key-lost) retrieval row reads as "not configured", and that ``GET /memory/pending`` answers 200 end to end.

[POS]
Real UserConfig rows in the isolated test database. Existing memory API tests override the manager dependency, so this
file is what proves the default-install path of the dependency itself.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete

from app.api.dependencies import get_deploy_identity
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.database.connection import get_session_factory
from app.database.models import UserConfig
from app.services.agent.platform_config import load_platform_retrieval_configs
from app.services.config.encryption import ConfigEncryptionService
from app.services.memory.extract_retry.resolve_chat_extraction_llm import (
    invalidate_platform_dedup_llm_cache,
    resolve_import_extraction_llm,
    resolve_platform_dedup_llm,
)
from tests.support.minimal_app import build_minimal_app

_CONFIG_KEYS = ("providers", "defaultModelConfig", "retrieval")
_EMBEDDING_ONLY_RETRIEVAL: dict[str, object] = {
    "embeddingApplied": True,
    "embeddingConfig": {"provider": "openai", "model": "text-embedding-3-small", "apiKey": "sk-embedding"},
}


def _local_encryption() -> ConfigEncryptionService:
    return ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)


async def _remove_config_rows() -> None:
    async with get_session_factory()() as session:
        await session.execute(delete(UserConfig).where(UserConfig.config_key.in_(_CONFIG_KEYS)))
        await session.commit()
    invalidate_user_configs_cache()
    invalidate_platform_dedup_llm_cache()


@pytest.fixture
async def fresh_install() -> AsyncIterator[None]:
    """No provider, no default model, no retrieval settings: what a just-installed client has."""
    await _remove_config_rows()
    yield
    await _remove_config_rows()


async def _seal_retrieval_row(encryption: ConfigEncryptionService, value: dict[str, object]) -> None:
    sealed, _ = encryption.encrypt_if_needed("retrieval", value)
    async with get_session_factory()() as session:
        session.add(
            UserConfig(
                id="pytest-fresh-install-retrieval",
                config_key="retrieval",
                config_value={"_cipher": sealed},
                is_encrypted=True,
                version="1_0",
                last_device_id="pytest",
            )
        )
        await session.commit()
    invalidate_user_configs_cache()


async def test_retrieval_configs_are_empty_without_any_setting(fresh_install: None) -> None:
    assert await load_platform_retrieval_configs() == (None, None)


async def test_embedding_config_loads_without_an_llm_provider(fresh_install: None, monkeypatch: pytest.MonkeyPatch) -> None:
    encryption = _local_encryption()
    monkeypatch.setattr("app.services.config.encryption.get_encryption_service", lambda: encryption)
    await _seal_retrieval_row(encryption, _EMBEDDING_ONLY_RETRIEVAL)

    embedding, reranker = await load_platform_retrieval_configs()

    assert embedding is not None
    assert embedding.api_key == "sk-embedding"
    assert embedding.model.endswith("text-embedding-3-small")
    assert reranker is None


async def test_retrieval_row_sealed_under_a_lost_key_reads_as_not_configured(
    fresh_install: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seal_retrieval_row(_local_encryption(), _EMBEDDING_ONLY_RETRIEVAL)
    replacement = _local_encryption()
    monkeypatch.setattr("app.services.config.encryption.get_encryption_service", lambda: replacement)

    assert await load_platform_retrieval_configs() == (None, None)


async def test_platform_dedup_llm_is_none_without_a_provider(fresh_install: None) -> None:
    assert await resolve_platform_dedup_llm() is None


async def test_import_extraction_llm_is_none_without_a_provider(fresh_install: None) -> None:
    assert await resolve_import_extraction_llm(None) is None


@pytest.fixture
def memory_app() -> Iterator[FastAPI]:
    app = build_minimal_app(preset="memory")
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield app


async def test_pending_endpoint_answers_on_a_fresh_install(fresh_install: None, memory_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=memory_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/memory/pending", headers={"Authorization": "Bearer test_token"})

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
