"""Integration tests for model-switch preflight streak consumption — real SQLite, real harness store.

Verifies the full chain without mocks:
- A real SQLite file backs ChatCompressionStreakStore
- register_chat_compression_streak_store wires it into the harness store registry
- record_compression_effectiveness increments the DB streak
- POST /model-switch-preflight reads the real streak and suppresses the warning
  when anti-thrash semantics apply (streak >= limit, tokens below safety net)
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.catalog import model_info

from app.services.chat.compact.compression_streak import (
    ChatCompressionStreakStore,
    register_chat_compression_streak_store,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _streak_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Real SQLite DB with a chats table, registered as the global streak store."""
    import sqlite3

    db_file = tmp_path / "preflight_streak.db"
    monkeypatch.setattr("app.config.settings.settings.database.sqlite_path", str(db_file))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE chats (id TEXT PRIMARY KEY, compression_ineffective_streak INTEGER NOT NULL DEFAULT 0)")
        conn.execute("INSERT INTO chats (id, compression_ineffective_streak) VALUES ('chat-1', 0)")
        conn.commit()

    register_chat_compression_streak_store()
    yield db_file
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        register_compression_streak_store,
    )

    register_compression_streak_store(None)


def _preflight_item(client: TestClient, *, estimated_tokens: int, chat_id: str | None = None) -> dict:
    body: dict[str, object] = {
        "estimated_tokens": estimated_tokens,
        "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
    }
    if chat_id is not None:
        body["chat_id"] = chat_id
    response = client.post(
        "/api/v1/integrations/llm/model-switch-preflight",
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["results"][0]


@pytest.mark.integration
def test_preflight_reads_real_db_streak_and_suppresses_warning(client: TestClient, _streak_sqlite: Path) -> None:
    """Real streak=2 in SQLite suppresses the compression warning below the safety net."""
    store = ChatCompressionStreakStore()
    store.set_streak("chat-1", 2)

    item = _preflight_item(client, estimated_tokens=9000, chat_id="chat-1")
    # threshold 8000; 9000 < 14400 (90% safety net) and streak=2 -> suppressed
    assert item["will_compress"] is False


@pytest.mark.integration
def test_preflight_reads_real_db_streak_but_safety_net_warns(client: TestClient, _streak_sqlite: Path) -> None:
    """streak=2 but tokens >= 90% window: safety net forces the warning."""
    store = ChatCompressionStreakStore()
    store.set_streak("chat-1", 2)

    item = _preflight_item(client, estimated_tokens=15000, chat_id="chat-1")
    # 15000 >= 14400 (90% of 16000) -> OOM guard overrides anti-thrash
    assert item["will_compress"] is True


@pytest.mark.integration
def test_preflight_without_chat_id_ignores_db_streak(client: TestClient, _streak_sqlite: Path) -> None:
    """Absent chat_id skips streak lookup entirely, warning stays on."""
    store = ChatCompressionStreakStore()
    store.set_streak("chat-1", 2)

    item = _preflight_item(client, estimated_tokens=9000)
    assert item["will_compress"] is True


@pytest.mark.integration
def test_record_effectiveness_persists_streak_visible_to_preflight(client: TestClient, _streak_sqlite: Path) -> None:
    """Compression effectiveness recording flows into the preflight decision."""
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
        record_compression_effectiveness,
    )

    record_compression_effectiveness(
        "chat-1",
        original_tokens=10_000,
        tokens_saved=40,
    )
    # First ineffectiveness -> streak 1 (below limit 2) -> warning stays
    item = _preflight_item(client, estimated_tokens=9000, chat_id="chat-1")
    assert item["will_compress"] is True

    record_compression_effectiveness(
        "chat-1",
        original_tokens=10_000,
        tokens_saved=40,
    )
    # Second ineffectiveness -> streak 2 -> warning suppressed
    item = _preflight_item(client, estimated_tokens=9000, chat_id="chat-1")
    assert item["will_compress"] is False


@pytest.mark.integration
def test_preflight_resolves_real_model_window_from_the_frontend_value(
    client: TestClient,
) -> None:
    """The window the frontend sends drives the threshold for a known production model."""
    from tests.support.test_secrets import resolve_test_env

    model = resolve_test_env("BASIC_MODEL", "openai-like/deepseek-v4-flash")
    if not model:
        pytest.skip("BASIC_MODEL not configured in .env.test")

    response = client.post(
        "/api/v1/integrations/llm/model-switch-preflight",
        json={
            "estimated_tokens": 5000,
            "models": [{"model": model, "max_input_tokens": 16000}],
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()["data"]["results"][0]
    assert item["found"] is True
    assert item["new_window"] == 16000
    assert item["compress_threshold"] is not None
    assert item["compress_threshold"] > 0


@pytest.mark.integration
def test_preflight_threshold_follows_the_window_not_the_model_name(
    client: TestClient,
) -> None:
    """A configured production model gets the default threshold: half of the window, like any other model."""
    from tests.support.test_secrets import resolve_test_env

    model = resolve_test_env("BASIC_MODEL", "openai-like/deepseek-v4-flash")
    if not model:
        pytest.skip("BASIC_MODEL not configured in .env.test")

    response = client.post(
        "/api/v1/integrations/llm/model-switch-preflight",
        json={
            "estimated_tokens": 5000,
            "models": [{"model": model, "max_input_tokens": 16000}],
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()["data"]["results"][0]
    assert item["found"] is True
    assert item["compress_threshold"] == int(item["new_window"] * 0.5)


@pytest.mark.integration
def test_preflight_real_catalog_model_lookup(client: TestClient) -> None:
    """A model the catalog knows resolves its window without frontend max_input_tokens."""
    native_model = "gpt-4o"
    assert model_info(native_model) is not None, f"{native_model} missing from the bundled model catalog"

    response = client.post(
        "/api/v1/integrations/llm/model-switch-preflight",
        json={
            "estimated_tokens": 5000,
            "models": [{"model": native_model}],
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()["data"]["results"][0]
    assert item["found"] is True
    assert item["new_window"] is not None
    assert item["new_window"] > 0
    assert item["compress_threshold"] is not None
