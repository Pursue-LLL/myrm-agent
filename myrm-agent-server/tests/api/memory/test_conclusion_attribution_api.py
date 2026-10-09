"""Integration tests for Conclusion Attribution and Chat Evidence API (Item 141).

Verifies conclusion creation, querying, tree traversals, ripple impact analysis,
cascade deletion, chat-with-evidence, and attribution metrics.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.conclusion_attribution_router import router as attribution_router
from app.services.memory.conclusion_attribution.provider import (
    ConclusionAttributionProvider,
)


@pytest.fixture(autouse=True)
def clean_provider() -> None:
    """Ensure clean provider instance for each test."""
    ConclusionAttributionProvider.reset_instance()


@pytest.fixture
def test_app() -> FastAPI:
    """Create test FastAPI application hosting the attribution router."""
    api_app = FastAPI()
    api_app.include_router(attribution_router)
    return api_app


@pytest.mark.asyncio
async def test_create_and_list_conclusions(test_app: FastAPI) -> None:
    """Verify creating conclusions and retrieving them via list endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Create explicit fact
        resp = await client.post(
            "/api/memory/attribution/conclusions",
            json={
                "peer_id": "alice",
                "content": "Alice prefers FastAPI for asynchronous backend microservices.",
                "level": "explicit",
                "confidence": 0.98,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        c1_id = data["conclusion"]["id"]
        assert data["conclusion"]["level"] == "explicit"

        # 2. List conclusions
        list_resp = await client.get("/api/memory/attribution/conclusions?peer_id=alice")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] == 1
        assert list_data["items"][0]["id"] == c1_id


@pytest.mark.asyncio
async def test_query_conclusions(test_app: FastAPI) -> None:
    """Verify semantic/keyword query endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/memory/attribution/conclusions",
            json={
                "peer_id": "bob",
                "content": "Bob uses Docker and Podman for local container sandboxing.",
                "level": "explicit",
            },
        )
        await client.post(
            "/api/memory/attribution/conclusions",
            json={
                "peer_id": "bob",
                "content": "Bob prefers React 19 and Vite for frontend bundling.",
                "level": "explicit",
            },
        )

        query_resp = await client.post(
            "/api/memory/attribution/query",
            json={"query": "Docker container", "peer_id": "bob"},
        )
        assert query_resp.status_code == 200
        items = query_resp.json()["items"]
        assert len(items) >= 1
        assert "Docker" in items[0]["content"]


@pytest.mark.asyncio
async def test_tree_downward_and_upward_endpoints(test_app: FastAPI) -> None:
    """Verify tree traversal endpoints in downward and upward directions."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Create Root
        r1 = (
            await client.post(
                "/api/memory/attribution/conclusions",
                json={"peer_id": "u", "content": "Root fact 1", "level": "explicit"},
            )
        ).json()["conclusion"]["id"]

        # Create Derived
        d1 = (
            await client.post(
                "/api/memory/attribution/conclusions",
                json={
                    "peer_id": "u",
                    "content": "Derived rule 1",
                    "level": "deductive",
                    "source_ids": [r1],
                },
            )
        ).json()["conclusion"]["id"]

        # Downward from d1
        down_resp = await client.get(f"/api/memory/attribution/tree/downward/{d1}")
        assert down_resp.status_code == 200
        down_data = down_resp.json()
        assert down_data["direction"] == "downward"
        assert len(down_data["nodes"]) == 2

        # Upward from r1
        up_resp = await client.get(f"/api/memory/attribution/tree/upward/{r1}")
        assert up_resp.status_code == 200
        up_data = up_resp.json()
        assert up_data["direction"] == "upward"
        assert len(up_data["nodes"]) == 2


@pytest.mark.asyncio
async def test_ripple_impact_endpoint(test_app: FastAPI) -> None:
    """Verify ripple impact calculation endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        r1 = (
            await client.post(
                "/api/memory/attribution/conclusions",
                json={"peer_id": "u", "content": "Foundational premise"},
            )
        ).json()["conclusion"]["id"]

        await client.post(
            "/api/memory/attribution/conclusions",
            json={
                "peer_id": "u",
                "content": "Dependent rule 1",
                "level": "deductive",
                "source_ids": [r1],
            },
        )

        impact_resp = await client.get(f"/api/memory/attribution/impact/{r1}")
        assert impact_resp.status_code == 200
        impact_data = impact_resp.json()
        assert impact_data["target_conclusion_id"] == r1
        assert len(impact_data["impacted_conclusion_ids"]) == 1
        assert impact_data["severity"] in ["low", "medium", "high", "critical"]


@pytest.mark.asyncio
async def test_chat_with_evidence_endpoint(test_app: FastAPI) -> None:
    """Verify chat endpoint providing transparent evidence package."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/memory/attribution/conclusions",
            json={
                "peer_id": "alice",
                "content": "Alice always specifies exact semver for python packages.",
                "level": "explicit",
            },
        )

        # 1. With evidence
        chat_resp = await client.post(
            "/api/memory/attribution/chat",
            json={
                "query": "How should I pin python versions?",
                "peer_id": "alice",
                "session_id": "sess_integration",
                "include_evidence": True,
            },
        )
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert "semver" in chat_data["reply"]
        assert chat_data["evidence"] is not None
        assert len(chat_data["evidence"]["conclusions"]) >= 1
        assert len(chat_data["evidence"]["messages"]) >= 1

        # 2. Without evidence
        chat_no_ev = await client.post(
            "/api/memory/attribution/chat",
            json={
                "query": "How should I pin python versions?",
                "peer_id": "alice",
                "include_evidence": False,
            },
        )
        assert chat_no_ev.status_code == 200
        assert chat_no_ev.json()["evidence"] is None


@pytest.mark.asyncio
async def test_delete_and_stats_endpoints(test_app: FastAPI) -> None:
    """Verify conclusion deletion and telemetry stats endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        c1 = (
            await client.post(
                "/api/memory/attribution/conclusions",
                json={"peer_id": "charlie", "content": "Charlie note 1"},
            )
        ).json()["conclusion"]["id"]

        # Check stats
        stats_resp = await client.get("/api/memory/attribution/stats?peer_id=charlie")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_conclusions"] == 1
        assert stats["explicit_count"] == 1

        # Delete
        del_resp = await client.delete(f"/api/memory/attribution/conclusions/{c1}")
        assert del_resp.status_code == 200
        assert c1 in del_resp.json()["deleted_ids"]
