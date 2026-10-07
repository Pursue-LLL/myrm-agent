# [POS]: tests/api/memory/test_peer_cognition_api.py
# [INPUT]: app.api.memory.peer_cognition_router, FastAPI app
# [OUTPUT]: Integration API tests for Peer-Centric Social Cognition and Persona Card Suite (Item 110)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.peer_cognition_router import (
    router as peer_cognition_router,
)
from app.services.memory.peer_cognition_service import (
    PeerCognitionService,
    get_peer_cognition_service,
)


@pytest.fixture
def isolated_service() -> PeerCognitionService:
    """Provides an isolated in-memory PeerCognitionService instance."""
    return PeerCognitionService()


@pytest.fixture
def test_app(isolated_service: PeerCognitionService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(peer_cognition_router, prefix="/api/memory")
    app.dependency_overrides[get_peer_cognition_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_register_and_list_peers_api(test_app: FastAPI) -> None:
    """Validate registering distinct peer types and filtering peer identities via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a user peer
        reg_user = await client.post(
            "/api/memory/peer-cognition/peers",
            json={
                "peer_id": "user_alice",
                "peer_type": "user_peer",
                "display_name": "Alice",
                "role_title": "Lead Software Architect",
            },
        )
        assert reg_user.status_code == 201
        data_user = reg_user.json()
        assert data_user["peer_id"] == "user_alice"
        assert data_user["peer_type"] == "user_peer"

        # 2. Register an agent peer
        reg_agent = await client.post(
            "/api/memory/peer-cognition/peers",
            json={
                "peer_id": "agent_reviewer",
                "peer_type": "agent_peer",
                "display_name": "ReviewerAgent",
                "role_title": "Automated Security Reviewer",
            },
        )
        assert reg_agent.status_code == 201

        # 3. List all peers
        list_all = await client.get("/api/memory/peer-cognition/peers")
        assert list_all.status_code == 200
        assert len(list_all.json()) >= 2

        # 4. Filter by agent_peer
        list_agents = await client.get("/api/memory/peer-cognition/peers?peer_type=agent_peer")
        assert list_agents.status_code == 200
        agents = list_agents.json()
        assert len(agents) == 1
        assert agents[0]["peer_id"] == "agent_reviewer"

        # 5. Get single peer
        get_res = await client.get("/api/memory/peer-cognition/peers/user_alice")
        assert get_res.status_code == 200
        assert get_res.json()["role_title"] == "Lead Software Architect"

        # 6. Not found
        nf_res = await client.get("/api/memory/peer-cognition/peers/unknown_peer")
        assert nf_res.status_code == 404


@pytest.mark.asyncio
async def test_persona_card_lifecycle_and_evolution_api(test_app: FastAPI) -> None:
    """Validate persona card retrieval, explicit mutation, and interaction evolution."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register peer
        await client.post(
            "/api/memory/peer-cognition/peers",
            json={
                "peer_id": "user_bob",
                "peer_type": "user_peer",
                "display_name": "Bob",
                "role_title": "DevOps Engineer",
            },
        )

        # 1. Update persona card
        update_res = await client.put(
            "/api/memory/peer-cognition/cards/user_bob",
            json={
                "core_responsibilities": ["Kubernetes Deployment", "CI/CD Pipeline"],
                "decision_style": "safe_gradual_rollout",
                "standing_preferences": {"orchestrator": "k8s", "ci": "GitHub Actions"},
            },
        )
        assert update_res.status_code == 200
        card = update_res.json()
        assert card["peer_id"] == "user_bob"
        assert "Kubernetes Deployment" in card["core_responsibilities"]
        assert card["standing_preferences"]["orchestrator"] == "k8s"

        # 2. Get persona card
        get_card = await client.get("/api/memory/peer-cognition/cards/user_bob")
        assert get_card.status_code == 200
        assert get_card.json()["decision_style"] == "safe_gradual_rollout"

        # 3. Record interaction outcome with evolution
        evolve_res = await client.post(
            "/api/memory/peer-cognition/cards/user_bob/interactions",
            json={
                "success": True,
                "preference_deltas": {"container_engine": "docker"},
            },
        )
        assert evolve_res.status_code == 200
        evolved_card = evolve_res.json()
        assert evolved_card["interaction_count"] == 1
        assert evolved_card["standing_preferences"]["container_engine"] == "docker"
        assert evolved_card["trust_score"] >= 0.9


@pytest.mark.asyncio
async def test_relational_edges_and_graph_topology_api(test_app: FastAPI) -> None:
    """Validate inserting and listing directed relational edges."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register peers
        await client.post(
            "/api/memory/peer-cognition/peers",
            json={"peer_id": "user_lead", "peer_type": "user_peer", "display_name": "LeadDev"},
        )
        await client.post(
            "/api/memory/peer-cognition/peers",
            json={"peer_id": "agent_bot", "peer_type": "agent_peer", "display_name": "DevBot"},
        )

        # 1. Add edge: user_lead collaborates_with agent_bot
        edge_res = await client.post(
            "/api/memory/peer-cognition/edges",
            json={
                "edge_id": "edge_collab_01",
                "source_peer_id": "user_lead",
                "target_entity_id": "agent_bot",
                "target_is_peer": True,
                "relation_kind": "collaborates_with",
                "context_note": "Pair programming on refactoring",
                "weight": 0.95,
            },
        )
        assert edge_res.status_code == 201
        data = edge_res.json()
        assert data["edge_id"] == "edge_collab_01"
        assert data["relation_kind"] == "collaborates_with"

        # 2. Get edges connected to user_lead
        list_edges = await client.get("/api/memory/peer-cognition/edges/user_lead")
        assert list_edges.status_code == 200
        edges = list_edges.json()
        assert len(edges) >= 1
        assert any(e["edge_id"] == "edge_collab_01" for e in edges)


@pytest.mark.asyncio
async def test_low_token_projection_generation_api(test_app: FastAPI) -> None:
    """Validate compiling low-token context prompt projection block via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register peers and populate cards
        await client.post(
            "/api/memory/peer-cognition/peers",
            json={"peer_id": "user_charlie", "peer_type": "user_peer", "display_name": "Charlie"},
        )
        await client.put(
            "/api/memory/peer-cognition/cards/user_charlie",
            json={
                "core_responsibilities": ["Frontend Architecture"],
                "decision_style": "accessible_responsive",
                "standing_preferences": {"ui_framework": "Vue3"},
            },
        )

        # Generate projection
        proj_res = await client.post(
            "/api/memory/peer-cognition/projection",
            json={"peer_ids": ["user_charlie"]},
        )
        assert proj_res.status_code == 200
        proj = proj_res.json()
        assert proj["token_cost_estimate"] > 0
        assert "Charlie" in proj["formatted_prompt_block"]
        assert "Frontend Architecture" in proj["formatted_prompt_block"]
        assert "Vue3" in proj["formatted_prompt_block"]
        assert proj["targeted_peers"] == ["user_charlie"]
