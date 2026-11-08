"""An embedding model saved through the settings routes reaches the FAQ interceptor.

[INPUT]
app.api.config.routes.crud (PUT /config/{key}, POST /config/sync)
app.services.faq.factory::get_faq_interceptor

[OUTPUT]
Proof that the next FAQ lookup embeds with the model saved last, whichever route saved it.

[POS]
Real routes, real config store and the real retrieval-settings loader with its cache; only the embedding backend and
the vector store are stubbed. The settings screen saves through POST /config/sync, so a reset wired to the PUT route
alone would leave the interceptor on the previous model.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.core.channel_bridge.model_resolver as model_resolver
import app.services.faq.factory as faq_factory
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.database.connection import get_session, init_database
from app.database.models import ConfigAuditLog, UserConfig
from tests.api.config.conftest import cleanup_shared_test_db
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)

SMALL = "text-embedding-3-small"
LARGE = "text-embedding-3-large"


def _retrieval(model: str, applied_at: int) -> dict[str, object]:
    return {
        "embeddingConfig": {"provider": "openai", "model": model, "apiKey": "placeholder-key", "apiBase": ""},
        "embeddingApplied": True,
        "embeddingAppliedAt": applied_at,
        "enableAdvancedRetrieval": False,
    }


def _saved_version() -> str | None:
    version = client.get("/api/v1/config/retrieval").json()["version"]
    return None if version == "0" else version


def _save_with_put(value: dict[str, object]) -> None:
    response = client.put(
        "/api/v1/config/retrieval", json={"value": value, "device_id": "d1", "expectedVersion": _saved_version()}
    )
    assert response.status_code == 200, response.text


def _save_with_sync(value: dict[str, object]) -> None:
    change = {"key": "retrieval", "value": value, "expectedVersion": _saved_version(), "timestamp": 1}
    response = client.post("/api/v1/config/sync", json={"changes": [change], "deviceId": "d1"})
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True, response.text


@contextmanager
def _stubbed_backends() -> Iterator[MagicMock]:
    """Yields the embedding-service factory, which records the config each interceptor is built with."""
    get_service = MagicMock(side_effect=lambda config: MagicMock(name=f"embedding_service_{config.model}"))
    with (
        patch("myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service", new=get_service),
        patch(
            "app.core.retriever.vector.defaults.create_default_vector_store",
            new=AsyncMock(return_value=MagicMock(name="vector_store")),
        ),
    ):
        yield get_service


async def _clear_saved_settings() -> None:
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    invalidate_user_configs_cache()


async def _nothing_configured() -> None:
    """With no embedding saved, the factory drops whatever interceptor an earlier test left cached."""
    await _clear_saved_settings()
    with _stubbed_backends():
        assert await faq_factory.get_faq_interceptor() is None


@pytest.fixture(scope="module", autouse=True)
def _own_schema() -> Iterator[None]:
    """Earlier modules delete the shared database file, so this one creates its schema itself, as they do."""
    asyncio.run(init_database())
    yield
    cleanup_shared_test_db(Path(os.environ["MYRM_DATA_DIR"]) / "data.db")


@pytest.fixture(autouse=True)
async def _fresh_settings(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    # The loader insists on a configured LLM provider; the retrieval path under test does not depend on it.
    monkeypatch.setattr(
        model_resolver, "_fallback_model_from_providers", lambda providers, sandbox: SimpleNamespace(model="stub")
    )
    monkeypatch.setattr(model_resolver, "enrich_model_context_window", lambda model_cfg, providers: model_cfg)
    await _nothing_configured()
    yield
    await _nothing_configured()


@pytest.mark.parametrize("save", [_save_with_put, _save_with_sync], ids=["PUT /config/{key}", "POST /config/sync"])
async def test_the_next_faq_lookup_embeds_with_the_model_saved_last(save: Callable[[dict[str, object]], None]) -> None:
    with _stubbed_backends() as get_service:
        save(_retrieval(SMALL, 1))
        before = await faq_factory.get_faq_interceptor()
        save(_retrieval(LARGE, 2))
        after = await faq_factory.get_faq_interceptor()

    assert before is not None
    assert after is not None
    assert after is not before
    built_with = [call.args[0].model.rsplit("/", 1)[-1] for call in get_service.call_args_list]
    assert built_with == [SMALL, LARGE]
