"""API integration tests for Multi-Human Multi-Agent Live Document Co-Authoring Ledger (Item 72).

[INPUT]
- app.api.agents.coauthoring_ledger_router.router
- app.services.agent.coauthoring_ledger_service.get_coauthoring_ledger_service

[OUTPUT]
- Pytest assertions verifying collaborator registration, block lease locks,
  granular delta ledger with intent attribution, human-priority conflict arbitration,
  and isolated staging proposals.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_coauthoring_ledger_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.coauthoring_ledger_router import router as coauthoring_ledger_router
from app.services.agent.coauthoring_ledger_service import get_coauthoring_ledger_service


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory sessions before each test."""
    service = get_coauthoring_ledger_service()
    service.reset_session("chat-test-coauth")


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with coauthoring_ledger_router attached."""
    app = FastAPI()
    app.include_router(coauthoring_ledger_router)
    return TestClient(app)


def test_register_and_list_collaborators_api(client: TestClient) -> None:
    """Test registering humans and associated AI agents into tripartite space."""
    # 1. Register Human
    resp_h = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/collaborators",
        json={
            "collaborator_id": "user-alice",
            "collaborator_type": "human",
            "name": "Alice Architect",
            "role_description": "System Design Lead",
        },
    )
    assert resp_h.status_code == 201
    assert resp_h.json()["collaborator_id"] == "user-alice"

    # 2. Register Agent bound to Human
    resp_a = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/collaborators",
        json={
            "collaborator_id": "bot-researcher",
            "collaborator_type": "agent",
            "name": "Research Copilot",
            "principal_human_id": "user-alice",
            "role_description": "Data Ingestion Specialist",
        },
    )
    assert resp_a.status_code == 201
    assert resp_a.json()["principal_human_id"] == "user-alice"

    # 3. List
    list_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/collaborators")
    assert list_resp.status_code == 200
    collabs = list_resp.json()
    assert len(collabs) == 2


def test_init_document_and_render_markdown_api(client: TestClient) -> None:
    """Test document block initialization and markdown document rendering."""
    payload = {
        "document_id": "doc-cloud-arch",
        "title": "Cloudflare Zero Trust Architecture",
        "blocks": [
            {
                "block_id": "b-h1",
                "block_type": "heading",
                "content": "Cloudflare Tunnel Setup",
                "version": 1,
                "last_author_id": "user-alice",
                "last_updated_at": 1000.0,
            },
            {
                "block_id": "b-p1",
                "block_type": "paragraph",
                "content": "Cloudflare Tunnel provides remote access without exposing public IPs.",
                "version": 1,
                "last_author_id": "user-alice",
                "last_updated_at": 1000.0,
            },
        ],
    }
    init_resp = client.post("/chats/chat-test-coauth/coauthoring-ledger/document/init", json=payload)
    assert init_resp.status_code == 200
    blocks = init_resp.json()
    assert len(blocks) == 2

    # Render markdown
    md_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/markdown")
    assert md_resp.status_code == 200
    md = md_resp.json()["markdown"]
    assert "# Cloudflare Zero Trust Architecture" in md
    assert "## Cloudflare Tunnel Setup" in md
    assert "Cloudflare Tunnel provides remote access" in md


def test_acquire_and_release_block_lease_api(client: TestClient) -> None:
    """Test acquiring and releasing block leases with 423 Locked collision protection."""
    client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/document/init",
        json={
            "document_id": "doc-lease",
            "title": "Lease Document",
            "blocks": [
                {
                    "block_id": "b-target",
                    "block_type": "paragraph",
                    "content": "Initial baseline statement.",
                    "version": 1,
                    "last_author_id": "init",
                    "last_updated_at": 1000.0,
                }
            ],
        },
    )

    # Alice acquires lease
    acq_resp = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/leases/acquire",
        json={"block_id": "b-target", "author_id": "user-alice", "duration_seconds": 60.0},
    )
    assert acq_resp.status_code == 200
    assert acq_resp.json()["acquired"] is True

    # Bob attempts to mutate without lease -> 423
    delta_fail = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/deltas",
        json={
            "block_id": "b-target",
            "operation": "update_block",
            "author_id": "user-bob",
            "new_content": "Unauthorized override by Bob",
            "intent_reason": "Forced update",
        },
    )
    assert delta_fail.status_code == 423

    # Alice releases lease
    rel_resp = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/leases/release",
        json={"block_id": "b-target", "author_id": "user-alice"},
    )
    assert rel_resp.status_code == 200
    assert rel_resp.json()["released"] is True

    # Bob can now mutate
    delta_ok = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/deltas",
        json={
            "block_id": "b-target",
            "operation": "update_block",
            "author_id": "user-bob",
            "new_content": "Authorized update by Bob after lease release",
            "intent_reason": "Approved revision",
        },
    )
    assert delta_ok.status_code == 200
    assert delta_ok.json()["version"] == 2


def test_apply_delta_and_attribution_ledger_api(client: TestClient) -> None:
    """Test delta insertion and querying immutable ledger entries with contributions."""
    client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/collaborators",
        json={
            "collaborator_id": "user-lead",
            "collaborator_type": "human",
            "name": "Team Lead",
        },
    )

    # 1. Apply Insert Delta
    ins_resp = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/deltas",
        json={
            "block_id": "b-intro",
            "operation": "insert_block",
            "author_id": "user-lead",
            "new_content": "Project Overview and Scope Definition.",
            "intent_reason": "Authoring opening section",
            "block_type": "paragraph",
        },
    )
    assert ins_resp.status_code == 200
    assert ins_resp.json()["version"] == 1

    # 2. Query deltas
    deltas_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/deltas?block_id=b-intro")
    assert deltas_resp.status_code == 200
    deltas = deltas_resp.json()
    assert len(deltas) == 1
    assert deltas[0]["intent_reason"] == "Authoring opening section"

    # 3. Contributions
    contrib_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/contributions")
    assert contrib_resp.status_code == 200
    assert contrib_resp.json()["user-lead"] == 1


def test_arbitrate_conflict_human_priority_api(client: TestClient) -> None:
    """Test arbitrating colliding edits where Human is prioritized and Agent is staged."""
    client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/collaborators",
        json={
            "collaborator_id": "user-alice",
            "collaborator_type": "human",
            "name": "Alice Human",
        },
    )
    client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/collaborators",
        json={
            "collaborator_id": "bot-ai",
            "collaborator_type": "agent",
            "name": "Bot AI",
            "principal_human_id": "user-alice",
        },
    )

    arb_payload = {
        "block_id": "b-clause",
        "first_author_id": "user-alice",
        "first_content": "Clause updated with SLA: 99.99% uptime required.",
        "first_reason": "Contractual SLA compliance",
        "second_author_id": "bot-ai",
        "second_content": "Clause reworded: 99.9% uptime target.",
        "second_reason": "AI conciseness edit",
        "strategy": "human_priority",
    }
    arb_resp = client.post("/chats/chat-test-coauth/coauthoring-ledger/arbitrate", json=arb_payload)
    assert arb_resp.status_code == 200
    data = arb_resp.json()
    assert data["resolved"] is True
    assert "99.99%" in data["winning_content"]
    assert len(data["staging_proposals"]) == 1
    assert data["staging_proposals"][0]["author_id"] == "bot-ai"

    # Verify conflict record listed
    conflicts_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/conflicts")
    assert conflicts_resp.status_code == 200
    assert len(conflicts_resp.json()) == 1


def test_accept_staging_proposal_api(client: TestClient) -> None:
    """Test reviewing and accepting an isolated staging proposal into the active block."""
    client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/document/init",
        json={
            "document_id": "doc-prop",
            "title": "Proposal Document",
            "blocks": [
                {
                    "block_id": "b-metric",
                    "block_type": "paragraph",
                    "content": "Initial metric baseline.",
                    "version": 1,
                    "last_author_id": "user-init",
                    "last_updated_at": 1000.0,
                }
            ],
        },
    )

    # Generate conflict creating a staging proposal
    arb_resp = client.post(
        "/chats/chat-test-coauth/coauthoring-ledger/arbitrate",
        json={
            "block_id": "b-metric",
            "first_author_id": "user-init",
            "first_content": "Human edit.",
            "first_reason": "Human baseline",
            "second_author_id": "bot-bench",
            "second_content": "Benchmark results: P99 8ms, Throughput 5000 RPS.",
            "second_reason": "Empirical benchmark insertion",
            "strategy": "human_priority",
        },
    )
    prop_id = arb_resp.json()["staging_proposals"][0]["proposal_id"]

    # List proposals
    props_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/proposals?block_id=b-metric")
    assert props_resp.status_code == 200
    assert len(props_resp.json()) == 1

    # Accept proposal
    accept_resp = client.post(
        f"/chats/chat-test-coauth/coauthoring-ledger/proposals/{prop_id}/accept",
        json={"reviewer_id": "user-lead"},
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"

    # Verify block updated in document
    blocks_resp = client.get("/chats/chat-test-coauth/coauthoring-ledger/blocks")
    assert blocks_resp.status_code == 200
    target_block = next(b for b in blocks_resp.json() if b["block_id"] == "b-metric")
    assert "P99 8ms" in target_block["content"]
    assert target_block["version"] == 2


def test_arbitrate_conflict_isolated_staging_api(client: TestClient) -> None:
    """Test isolating both competing mutations as proposals when isolated_staging strategy is chosen."""
    arb_payload = {
        "block_id": "b-parallel",
        "first_author_id": "agent-worker-1",
        "first_content": "Option A: Rust Microservices.",
        "first_reason": "Performance rationale",
        "second_author_id": "agent-worker-2",
        "second_content": "Option B: Go Microservices.",
        "second_reason": "Simplicity rationale",
        "strategy": "isolated_staging_proposal",
    }
    arb_resp = client.post("/chats/chat-test-coauth/coauthoring-ledger/arbitrate", json=arb_payload)
    assert arb_resp.status_code == 200
    data = arb_resp.json()
    assert data["resolved"] is True
    assert len(data["staging_proposals"]) == 2
    assert "Both competing mutations isolated" in data["summary"]
