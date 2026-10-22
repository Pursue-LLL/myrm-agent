"""Unit tests for Hierarchical Leader-Worker Debate & Synthesis Pattern API endpoints.

[INPUT]
- app.api.agents.debate_synthesis_router.router
- app.services.agent.debate_synthesis_service.DebateSynthesisService

[OUTPUT]
- Pytest test cases verifying workflow creation, leader decomposition, specialist proposal submission,
  cross-debate rounds, and multi-dimensional trade-off matrix synthesis.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_debate_synthesis_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.debate_synthesis_router import (
    get_debate_synthesis_service,
)
from app.api.agents.debate_synthesis_router import (
    router as debate_synthesis_router,
)
from app.services.agent.debate_synthesis_service import (
    DebateSynthesisService,
)


@pytest.fixture
def mock_synthesis_service() -> DebateSynthesisService:
    return DebateSynthesisService()


@pytest.fixture
def synthesis_client(
    mock_synthesis_service: DebateSynthesisService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(debate_synthesis_router)
    app.dependency_overrides[get_debate_synthesis_service] = lambda: mock_synthesis_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_synthesis_workflow_lifecycle_and_decomposition(synthesis_client: TestClient) -> None:
    chat_id = "chat-syn-001"

    # 1. Create synthesis workflow
    create_payload = {
        "workflow_id": "wf-syn-test",
        "topic": "Evaluate Multi-Cloud Active-Active Database Architecture",
        "leader_id": "leader-codex",
        "researcher_id": "researcher-claude",
        "auditor_id": "auditor-sec",
        "max_rounds": 2,
    }
    resp = synthesis_client.post(f"/chats/{chat_id}/debate-synthesis", json=create_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["workflow_id"] == "wf-syn-test"
    assert body["data"]["phase"] == "decomposition"
    assert len(body["data"]["participants"]) == 3

    # 2. Get workflow
    get_resp = synthesis_client.get(f"/chats/{chat_id}/debate-synthesis/wf-syn-test")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["topic"] == "Evaluate Multi-Cloud Active-Active Database Architecture"

    # 3. Non-leader cannot decompose (403)
    bad_decomp = synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-syn-test/decompose",
        json={"leader_agent_id": "researcher-claude"},
    )
    assert bad_decomp.status_code == 403

    # 4. Designated leader decomposes subtask DAG
    decomp_resp = synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-syn-test/decompose",
        json={"leader_agent_id": "leader-codex"},
    )
    assert decomp_resp.status_code == 200
    decomp_data = decomp_resp.json()["data"]
    assert decomp_data["phase"] == "research_discovery"
    assert len(decomp_data["subtasks"]) == 2
    # Verify dependency topological link
    res_task = decomp_data["subtasks"][0]
    aud_task = decomp_data["subtasks"][1]
    assert aud_task["depends_on"] == [res_task["task_id"]]


def test_proposals_cross_debate_and_tradeoff_matrix_synthesis(
    synthesis_client: TestClient,
) -> None:
    chat_id = "chat-syn-002"

    # 1. Create & decompose workflow
    create_payload = {
        "workflow_id": "wf-matrix-test",
        "topic": "Adopt GraphQL Federation vs tRPC in Microservices",
        "leader_id": "leader-codex",
        "researcher_id": "researcher-claude",
        "auditor_id": "auditor-sec",
    }
    synthesis_client.post(f"/chats/{chat_id}/debate-synthesis", json=create_payload)
    synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-matrix-test/decompose",
        json={"leader_agent_id": "leader-codex"},
    )

    # 2. Researcher submits Proposal A
    prop_a = {
        "proposal_id": "prop-federation",
        "title": "Apollo GraphQL Federation 2.0",
        "author_role": "research_analyst",
        "author_agent_id": "researcher-claude",
        "summary": "Unified enterprise schema gateway with subgraph routing.",
        "pros": ["Universal client gateway", "Decoupled subgraphs across teams"],
        "cons": ["Gateway proxy latency overhead", "Complex schema stitching"],
        "dimension_scores": {
            "performance": 0.70,
            "cost_efficiency": 0.80,
            "implementation_complexity": 0.50,
            "reliability": 0.90,
            "maintainability": 0.85,
        },
    }
    resp_prop_a = synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-matrix-test/proposals",
        json=prop_a,
    )
    assert resp_prop_a.status_code == 200
    assert resp_prop_a.json()["data"]["phase"] == "feasibility_critique"

    # 3. Auditor submits Proposal B
    prop_b = {
        "proposal_id": "prop-trpc",
        "title": "End-to-End Type-Safe tRPC Router",
        "author_role": "feasibility_auditor",
        "author_agent_id": "auditor-sec",
        "summary": "Lightweight RPC router with compile-time type guarantees.",
        "pros": ["Zero schema compile overhead", "Sub-millisecond serialization", "High developer velocity"],
        "cons": ["TypeScript-only tight coupling"],
        "dimension_scores": {
            "performance": 0.95,
            "cost_efficiency": 0.90,
            "implementation_complexity": 0.85,
            "reliability": 0.92,
            "maintainability": 0.90,
        },
    }
    resp_prop_b = synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-matrix-test/proposals",
        json=prop_b,
    )
    assert resp_prop_b.status_code == 200
    assert resp_prop_b.json()["data"]["phase"] == "cross_debate"

    # 4. Advance debate round
    adv_resp = synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-matrix-test/advance-debate",
    )
    assert adv_resp.status_code == 200

    # 5. Leader synthesizes multi-dimensional trade-off matrix
    synth_req = {
        "custom_weights": {
            "performance": 1.5,
            "cost_efficiency": 1.0,
            "implementation_complexity": 1.2,
            "reliability": 1.0,
            "maintainability": 1.0,
        },
        "custom_rationale": "tRPC selected due to significantly higher developer velocity and performance benefits.",
    }
    synth_resp = synthesis_client.post(
        f"/chats/{chat_id}/debate-synthesis/wf-matrix-test/synthesize",
        json=synth_req,
    )
    assert synth_resp.status_code == 200
    matrix = synth_resp.json()["data"]

    assert matrix["workflow_id"] == "wf-matrix-test"
    assert matrix["winner_proposal_id"] == "prop-trpc"
    assert "tRPC selected" in matrix["recommendation_rationale"]
    assert len(matrix["proposals"]) == 2

    # Verify winning proposal has is_recommended flag
    winning = next(p for p in matrix["proposals"] if p["proposal_id"] == "prop-trpc")
    assert winning["is_recommended"] is True
