"""API integration tests for Council of Agents Multi-Model Deliberation Protocol (Item 65).

[INPUT]
- app.api.agents.council_router.router
- app.services.agent.council_service.CouncilDeliberationService

[OUTPUT]
- Pytest assertions verifying session lifecycle, proposal submission, cross-critiques,
  rebuttals, and consensus synthesis API endpoints.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_council_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.council_router import router as council_router
from app.services.agent.council_service import CouncilDeliberationService


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory council sessions before each test."""
    CouncilDeliberationService.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with council_router attached."""
    app = FastAPI()
    app.include_router(council_router)
    return TestClient(app)


def test_create_and_get_session_api(client: TestClient) -> None:
    """Test creating a council deliberation session and retrieving its state."""
    create_payload = {
        "session_id": "sess-arch-01",
        "deliberation_topic": "Serverless vs Kubernetes for Agent Orchestration",
    }
    resp = client.post("/agents/council/sessions", json=create_payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["session_id"] == "sess-arch-01"
    assert data["deliberation_topic"] == "Serverless vs Kubernetes for Agent Orchestration"
    assert data["phase"] == "blind_proposal"
    assert len(data["proposals"]) == 0

    get_resp = client.get("/agents/council/sessions/sess-arch-01")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["session_id"] == "sess-arch-01"


def test_list_sessions_api(client: TestClient) -> None:
    """Test listing all active council sessions."""
    client.post(
        "/agents/council/sessions",
        json={"session_id": "sess-1", "deliberation_topic": "Topic 1"},
    )
    client.post(
        "/agents/council/sessions",
        json={"session_id": "sess-2", "deliberation_topic": "Topic 2"},
    )

    resp = client.get("/agents/council/sessions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2


def test_submit_proposal_api(client: TestClient) -> None:
    """Test submitting an independent model proposal into a council session."""
    client.post(
        "/agents/council/sessions",
        json={"session_id": "sess-prop", "deliberation_topic": "Vector Store Engine"},
    )

    prop_payload = {
        "proposal": {
            "proposal_id": "prop-qdrant",
            "member_id": "agent-claude",
            "model_name": "Claude-3.5-Sonnet",
            "title": "Qdrant Hybrid Vector Store",
            "reasoning_steps": ["High filtering capability", "Rust-based performance"],
            "key_arguments": ["Payload filtering efficiency", "Distributed deployment"],
            "confidence_score": 0.94,
        }
    }
    resp = client.post("/agents/council/sessions/sess-prop/proposals", json=prop_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "prop-qdrant" in data["proposals"]
    assert data["proposals"]["prop-qdrant"]["model_name"] == "Claude-3.5-Sonnet"


def test_submit_critique_and_rebuttal_api(client: TestClient) -> None:
    """Test posting a cross-critique and adding a defense rebuttal."""
    client.post(
        "/agents/council/sessions",
        json={"session_id": "sess-crit", "deliberation_topic": "Database Model"},
    )
    client.post(
        "/agents/council/sessions/sess-crit/proposals",
        json={
            "proposal": {
                "proposal_id": "prop-pg",
                "member_id": "agent-gpt",
                "model_name": "GPT-4o",
                "title": "PostgreSQL with pgvector",
                "confidence_score": 0.88,
            }
        },
    )

    critique_payload = {
        "critique": {
            "critique_id": "crit-scale",
            "source_member_id": "agent-claude",
            "target_member_id": "agent-gpt",
            "target_proposal_id": "prop-pg",
            "critique_points": ["Index rebuilds degrade write throughput at 10M+ vectors."],
            "severity": "high",
        }
    }
    resp = client.post("/agents/council/sessions/sess-crit/critiques", json=critique_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["critiques"]) == 1
    assert data["critiques"][0]["critique_id"] == "crit-scale"

    # Post rebuttal
    rebuttal_payload = {
        "rebuttal_text": "HNSW graphs with partial index partitioning resolve write degradation.",
    }
    reb_resp = client.post(
        "/agents/council/sessions/sess-crit/critiques/crit-scale/rebuttal",
        json=rebuttal_payload,
    )
    assert reb_resp.status_code == 200
    reb_data = reb_resp.json()["data"]
    assert reb_data["critiques"][0]["defense_rebuttal"] is not None


def test_advance_phase_and_consensus_synthesis_api(client: TestClient) -> None:
    """Test advancing deliberation phase and generating consensus verdict."""
    client.post(
        "/agents/council/sessions",
        json={"session_id": "sess-adv", "deliberation_topic": "RPC Framework"},
    )
    client.post(
        "/agents/council/sessions/sess-adv/proposals",
        json={
            "proposal": {
                "proposal_id": "p-grpc",
                "member_id": "m1",
                "model_name": "Claude-3.5-Sonnet",
                "title": "gRPC with Protobuf",
                "key_arguments": ["Strict schema contracts", "HTTP/2 multiplexing"],
                "confidence_score": 0.95,
            }
        },
    )

    adv_resp = client.post(
        "/agents/council/sessions/sess-adv/advance",
        json={"target_phase": "consensus_synthesis"},
    )
    assert adv_resp.status_code == 200
    data = adv_resp.json()["data"]
    assert data["phase"] == "consensus_synthesis"
    assert data["consensus"] is not None
    verdict = data["consensus"]
    assert "gRPC with Protobuf" in verdict["final_decision"]
    assert verdict["confidence_rating"] > 0.8
    assert "Claude-3.5-Sonnet" in verdict["participating_models"]


def test_session_not_found_errors(client: TestClient) -> None:
    """Test 404 responses when targeting non-existent council sessions."""
    get_404 = client.get("/agents/council/sessions/non-existent-session")
    assert get_404.status_code == 404

    prop_404 = client.post(
        "/agents/council/sessions/non-existent-session/proposals",
        json={
            "proposal": {
                "proposal_id": "p",
                "member_id": "m",
                "model_name": "mod",
                "title": "title",
            }
        },
    )
    assert prop_404.status_code == 404
