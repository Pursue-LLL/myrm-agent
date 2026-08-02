"""Integration tests for FAQ API — uses ASGI transport (no live server needed).

Covers: corpus CRUD, entry CRUD, bulk import, stats, unmatched queries,
boundary validation, and 404 handling.
"""

from __future__ import annotations

from importlib import import_module

import httpx
import pytest
from fastapi import FastAPI

AGENT_ID = "integration-test-faq-agent"


@pytest.fixture(scope="module")
def faq_app() -> FastAPI:
    app = FastAPI(title="FAQ Integration Test")
    faq_module = import_module("app.api.faq.router")
    app.include_router(faq_module.router, prefix="/api/v1/faq", tags=["faq"])
    return app


@pytest.fixture
async def client(faq_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=faq_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1/faq") as c:
        yield c


@pytest.mark.asyncio
async def test_faq_full_lifecycle(client: httpx.AsyncClient) -> None:
    """Full lifecycle: create corpus -> add entries -> list -> update -> stats -> delete."""

    # 1. GET corpus (auto-create)
    r = await client.get(f"/{AGENT_ID}/corpus")
    assert r.status_code == 200, f"get corpus failed: {r.text}"
    corpus = r.json()
    assert corpus["agent_id"] == AGENT_ID
    assert corpus["enabled"] is True
    assert corpus["entry_count"] == 0

    # 2. PATCH corpus settings
    r = await client.patch(
        f"/{AGENT_ID}/corpus",
        json={"threshold": 0.88, "min_score_gap": 0.20},
    )
    assert r.status_code == 200, f"patch corpus failed: {r.text}"
    updated = r.json()
    assert updated["threshold"] == 0.88
    assert updated["min_score_gap"] == 0.20

    # 3. POST single entry
    r = await client.post(
        f"/{AGENT_ID}/entries",
        json={"question": "How to reset password?", "answer": "Go to Settings > Security.", "tags": "security"},
    )
    assert r.status_code == 201, f"create entry failed: {r.text}"
    entry1 = r.json()
    assert entry1["question"] == "How to reset password?"
    entry1_id = entry1["id"]

    # 4. POST second entry
    r = await client.post(
        f"/{AGENT_ID}/entries",
        json={"question": "How to contact support?", "answer": "Email support@example.com."},
    )
    assert r.status_code == 201
    entry2_id = r.json()["id"]

    # 5. GET entries list
    r = await client.get(f"/{AGENT_ID}/entries")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 2
    entry_ids = [e["id"] for e in entries]
    assert entry1_id in entry_ids
    assert entry2_id in entry_ids

    # 6. PUT update entry
    r = await client.put(
        f"/entries/{entry1_id}",
        json={"question": "How to change password?"},
    )
    assert r.status_code == 200, f"update entry failed: {r.text}"
    assert r.json()["question"] == "How to change password?"

    # 7. POST bulk import
    r = await client.post(
        f"/{AGENT_ID}/import",
        json={
            "items": [
                {"question": "What is pricing?", "answer": "See pricing page."},
                {"question": "Where are docs?", "answer": "At docs.example.com."},
            ]
        },
    )
    assert r.status_code == 200, f"bulk import failed: {r.text}"
    assert r.json()["imported"] == 2

    # 8. GET stats
    r = await client.get(f"/{AGENT_ID}/stats")
    assert r.status_code == 200
    stats = r.json()
    assert "total" in stats
    assert "hits" in stats
    assert "misses" in stats
    assert "hit_rate" in stats

    # 9. GET unmatched
    r = await client.get(f"/{AGENT_ID}/unmatched")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 10. GET corpus entry_count updated
    r = await client.get(f"/{AGENT_ID}/corpus")
    assert r.status_code == 200
    assert r.json()["entry_count"] >= 4

    # 11. DELETE entries (cleanup)
    r = await client.get(f"/{AGENT_ID}/entries")
    all_entries = r.json()
    for e in all_entries:
        dr = await client.delete(f"/entries/{e['id']}")
        assert dr.status_code == 204, f"delete entry {e['id']} failed: {dr.text}"

    # 12. Verify empty
    r = await client.get(f"/{AGENT_ID}/entries")
    assert r.status_code == 200
    assert len(r.json()) == 0


@pytest.mark.asyncio
async def test_update_nonexistent_entry(client: httpx.AsyncClient) -> None:
    r = await client.put(
        "/entries/nonexistent-id-12345",
        json={"question": "test"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_entry(client: httpx.AsyncClient) -> None:
    r = await client.delete("/entries/nonexistent-id-12345")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_corpus_settings_boundary_clamp(client: httpx.AsyncClient) -> None:
    """Pydantic schema rejects threshold < 0.75."""
    r = await client.patch(
        f"/{AGENT_ID}/corpus",
        json={"threshold": 0.50},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_empty_bulk_import_rejected(client: httpx.AsyncClient) -> None:
    """Pydantic schema rejects empty items list (min_length=1)."""
    r = await client.post(
        f"/{AGENT_ID}/import",
        json={"items": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_entry_validation_rejects_empty_question(client: httpx.AsyncClient) -> None:
    """Pydantic schema rejects empty question (min_length=1)."""
    r = await client.post(
        f"/{AGENT_ID}/entries",
        json={"question": "", "answer": "some answer"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_entry_validation_rejects_empty_answer(client: httpx.AsyncClient) -> None:
    """Pydantic schema rejects empty answer (min_length=1)."""
    r = await client.post(
        f"/{AGENT_ID}/entries",
        json={"question": "valid question", "answer": ""},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_corpus_enabled_toggle(client: httpx.AsyncClient) -> None:
    """Toggle corpus enabled flag and verify state persists."""
    r = await client.patch(
        f"/{AGENT_ID}/corpus",
        json={"enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = await client.get(f"/{AGENT_ID}/corpus")
    assert r.json()["enabled"] is False

    r = await client.patch(
        f"/{AGENT_ID}/corpus",
        json={"enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True


@pytest.mark.asyncio
async def test_entry_update_preserves_unchanged_fields(client: httpx.AsyncClient) -> None:
    """PUT with only question should preserve answer and tags."""
    r = await client.post(
        f"/{AGENT_ID}/entries",
        json={"question": "Original Q", "answer": "Original A", "tags": "keep-me"},
    )
    assert r.status_code == 201
    eid = r.json()["id"]

    r = await client.put(f"/entries/{eid}", json={"question": "Updated Q"})
    assert r.status_code == 200
    data = r.json()
    assert data["question"] == "Updated Q"
    assert data["answer"] == "Original A"
    assert data["tags"] == "keep-me"

    await client.delete(f"/entries/{eid}")


@pytest.mark.asyncio
async def test_entry_strips_whitespace(client: httpx.AsyncClient) -> None:
    """Verify leading/trailing whitespace is stripped from question/answer/tags."""
    r = await client.post(
        f"/{AGENT_ID}/entries",
        json={"question": "  Padded Q  ", "answer": "  Padded A  ", "tags": "  t1  "},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["question"] == "Padded Q"
    assert data["answer"] == "Padded A"
    assert data["tags"] == "t1"

    await client.delete(f"/entries/{data['id']}")


@pytest.mark.asyncio
async def test_rebuild_index_without_vector_store_returns_503(client: httpx.AsyncClient) -> None:
    """rebuild-index should return 503 when vector store is unavailable."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "app.core.retriever.vector.defaults.create_default_vector_store",
        new_callable=AsyncMock,
        return_value=None,
    ):
        r = await client.post(f"/{AGENT_ID}/rebuild-index")

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_corpus_settings_max_threshold(client: httpx.AsyncClient) -> None:
    """Pydantic rejects threshold > 1.0."""
    r = await client.patch(
        f"/{AGENT_ID}/corpus",
        json={"threshold": 1.5},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_corpus_settings_negative_gap(client: httpx.AsyncClient) -> None:
    """Pydantic rejects min_score_gap < 0."""
    r = await client.patch(
        f"/{AGENT_ID}/corpus",
        json={"min_score_gap": -0.1},
    )
    assert r.status_code == 422
