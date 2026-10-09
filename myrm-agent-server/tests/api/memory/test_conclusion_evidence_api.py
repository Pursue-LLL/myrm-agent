"""Integration tests for Conclusion Attribution & Chat Evidence API.

[POS]
Tests verifying attributed conclusions declaration, causality DAG traversal,
cycle defense, and on-demand verifiable chat evidence retrieval.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.conclusion_evidence_router (router)
- app.services.memory.conclusion_evidence.provider (reset_conclusion_evidence_suite)

[OUTPUT]
- Test functions covering conclusion evidence API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    MessageEvidenceItem,
    ToolCallEvidenceItem,
)

from app.api.memory.conclusion_evidence_router import (
    router as conclusion_evidence_router,
)
from app.services.memory.conclusion_evidence.provider import (
    get_conclusion_evidence_suite,
    reset_conclusion_evidence_suite,
)


@pytest.fixture(autouse=True)
def reset_suite_before_test() -> None:
    """Reset conclusion evidence suite before each test."""
    reset_conclusion_evidence_suite()


@pytest.fixture
def test_app() -> FastAPI:
    """Create FastAPI test application with conclusion evidence router."""
    api_app = FastAPI()
    api_app.include_router(conclusion_evidence_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_declare_attributed_conclusion_and_query(test_app: FastAPI) -> None:
    """Verify declaring conclusion returns normative record with attribution fields."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # Declare C1
        resp = await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "c_alice_01",
                "peer_id": "alice",
                "content": "Alice prefers concise outputs and strict typing",
                "level": "explicit",
                "source_ids": [],
                "evidence_message_ids": ["msg_001"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conclusion_id"] == "c_alice_01"
        assert data["level"] == "explicit"
        assert data["times_derived"] == 1

        # Query single
        get_resp = await client.get("/api/memory/conclusion-evidence/conclusions/c_alice_01")
        assert get_resp.status_code == 200
        assert get_resp.json()["conclusion_id"] == "c_alice_01"

        # 404 on nonexistent
        missing_resp = await client.get("/api/memory/conclusion-evidence/conclusions/c_missing")
        assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_derivation_chain_and_cycle_prevention(test_app: FastAPI) -> None:
    """Verify DAG derivation links and cycle rejection."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # Add premise
        await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "c_root",
                "peer_id": "system",
                "content": "Root rule: Always enforce security gate",
                "level": "explicit",
            },
        )

        # Add derivative
        deriv_resp = await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "c_child",
                "peer_id": "system",
                "content": "Child deduction: Deny unapproved egress",
                "level": "deductive",
                "source_ids": ["c_root"],
            },
        )
        assert deriv_resp.status_code == 200
        assert deriv_resp.json()["source_ids"] == ["c_root"]

        # Attempt self-referential cycle -> 400 Bad Request
        cycle_resp = await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "c_cyclic",
                "peer_id": "system",
                "content": "Self cyclic rule",
                "level": "contradiction",
                "source_ids": ["c_cyclic"],
            },
        )
        assert cycle_resp.status_code == 400
        assert "cycle detected" in cycle_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_traversal_endpoints(test_app: FastAPI) -> None:
    """Verify upstream premises and downstream derivatives traversal endpoints."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "p1",
                "peer_id": "user",
                "content": "Premise 1",
                "level": "explicit",
            },
        )
        await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "d1",
                "peer_id": "user",
                "content": "Derivative 1",
                "level": "deductive",
                "source_ids": ["p1"],
            },
        )

        # Query derivatives of p1
        deriv_resp = await client.get("/api/memory/conclusion-evidence/conclusions/p1/derivatives")
        assert deriv_resp.status_code == 200
        deriv_list = deriv_resp.json()
        assert len(deriv_list) == 1
        assert deriv_list[0]["conclusion_id"] == "d1"

        # Query premises of d1
        prem_resp = await client.get("/api/memory/conclusion-evidence/conclusions/d1/premises")
        assert prem_resp.status_code == 200
        prem_list = prem_resp.json()
        assert len(prem_list) == 1
        assert prem_list[0]["conclusion_id"] == "p1"

        # Traversal view
        trav_resp = await client.get("/api/memory/conclusion-evidence/conclusions/d1/traversal")
        assert trav_resp.status_code == 200
        trav_data = trav_resp.json()
        assert len(trav_data["upstream_premises"]) == 1
        assert trav_data["upstream_premises"][0]["conclusion_id"] == "p1"


@pytest.mark.asyncio
async def test_chat_with_evidence_endpoints(test_app: FastAPI) -> None:
    """Verify chat_with_evidence endpoint behavior under include_evidence flags."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # Prepopulate harness service with message & tool traces
        suite = get_conclusion_evidence_suite()
        suite.register_message_evidence(
            MessageEvidenceItem(
                message_id="msg_auth_1",
                session_id="sess_100",
                peer_id="alice",
                content_snippet="I only review PRs with tests.",
            )
        )
        suite.record_tool_call(
            ToolCallEvidenceItem(
                tool_name="git_status",
                tool_input={"repo": "main"},
                tool_output="clean",
            )
        )

        # Declare conclusion referencing msg_auth_1
        await client.post(
            "/api/memory/conclusion-evidence/conclusions",
            json={
                "conclusion_id": "c_pr_rules",
                "peer_id": "alice",
                "content": "Alice requires automated tests on every PR",
                "level": "explicit",
                "evidence_message_ids": ["msg_auth_1"],
            },
        )

        # Chat without evidence (zero token overhead)
        plain_resp = await client.post(
            "/api/memory/conclusion-evidence/chat-with-evidence",
            json={
                "query": "PR tests",
                "peer_id": "alice",
                "include_evidence": False,
            },
        )
        assert plain_resp.status_code == 200
        assert "automated tests" in plain_resp.json()["content"]
        assert plain_resp.json()["evidence"] is None

        # Chat with evidence (verifiable audit mode)
        audit_resp = await client.post(
            "/api/memory/conclusion-evidence/chat-with-evidence",
            json={
                "query": "PR tests",
                "peer_id": "alice",
                "include_evidence": True,
            },
        )
        assert audit_resp.status_code == 200
        data = audit_resp.json()
        assert "automated tests" in data["content"]
        assert data["evidence"] is not None
        assert len(data["evidence"]["conclusions"]) == 1
        assert len(data["evidence"]["messages"]) == 1
        assert data["evidence"]["messages"][0]["message_id"] == "msg_auth_1"


@pytest.mark.asyncio
async def test_stats_endpoint(test_app: FastAPI) -> None:
    """Verify stats endpoint returns valid graph topology metrics."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        stats_resp = await client.get("/api/memory/conclusion-evidence/stats")
        assert stats_resp.status_code == 200
        data = stats_resp.json()
        assert "total_conclusions" in data
        assert "total_edges" in data
        assert "max_derivation_depth" in data
