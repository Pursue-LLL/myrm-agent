# [POS]: tests/api/memory/test_tiered_consensus_api.py
# [INPUT]: app.api.memory.tiered_consensus_router, FastAPI app
# [OUTPUT]: Integration API tests for Tiered Memory Hierarchy & Proposed Consensus Flow (Item 114)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.tiered_consensus_router import (
    router as tiered_consensus_router,
)
from app.services.memory.tiered_consensus_service import (
    TieredConsensusService,
    get_tiered_consensus_service,
)


@pytest.fixture
def isolated_service() -> TieredConsensusService:
    """Provides an isolated in-memory TieredConsensusService instance."""
    return TieredConsensusService()


@pytest.fixture
def test_app(isolated_service: TieredConsensusService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(tiered_consensus_router, prefix="/api/memory")
    app.dependency_overrides[get_tiered_consensus_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_propose_tiered_records_and_scoping_api(test_app: FastAPI) -> None:
    """Validate creating personal, project, and team consensus memory records via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Personal tier: Auto-approved immediately
        res_personal = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "personal",
                "content": "User prefers concise git commit messages without emojis",
                "owner_peer_id": "user_architect",
            },
        )
        assert res_personal.status_code == 201
        data_personal = res_personal.json()
        assert data_personal["status"] == "approved"
        assert data_personal["scope_tier"] == "personal"

        # 2. Project tier missing project_id should return 400
        res_err = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "project",
                "content": "Backend uses FastAPI on port 8000",
                "owner_peer_id": "agent_coder",
                "project_id": None,
            },
        )
        assert res_err.status_code == 400
        assert "project_id is strictly required" in res_err.json()["detail"]

        # 3. Project tier with project_id: Auto-approved
        res_proj = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "project",
                "content": "Backend uses FastAPI on port 8000",
                "owner_peer_id": "agent_coder",
                "project_id": "open-perplexity",
            },
        )
        assert res_proj.status_code == 201
        assert res_proj.json()["status"] == "approved"

        # 4. Team consensus tier: Initial status is forced proposed
        res_team = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "team_consensus",
                "content": "All API endpoints must include comprehensive integration tests",
                "owner_peer_id": "agent_reviewer",
                "rationale": "Code quality policy",
            },
        )
        assert res_team.status_code == 201
        team_data = res_team.json()
        assert team_data["status"] == "proposed"
        assert team_data["scope_tier"] == "team_consensus"
        team_record_id = team_data["record_id"]

        # 5. Idempotent deduplication returns existing record
        res_dup = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "team_consensus",
                "content": "  ALL API endpoints must include comprehensive integration tests  ",
                "owner_peer_id": "agent_reviewer",
            },
        )
        assert res_dup.status_code == 201
        assert res_dup.json()["record_id"] == team_record_id


@pytest.mark.asyncio
async def test_approval_flow_and_anti_self_approval_api(test_app: FastAPI) -> None:
    """Validate approval flow, anti-self-approval enforcement, and query safety filtering."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Propose draft rule by agent
        propose_res = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "team_consensus",
                "content": "Strict zero Any typing rule across Python codebase",
                "owner_peer_id": "agent_linter",
            },
        )
        assert propose_res.status_code == 201
        record_id = propose_res.json()["record_id"]

        # 2. Agent cannot self-approve its own team proposal (should return 403)
        self_approve_res = await client.post(
            f"/api/memory/tiered-consensus/records/{record_id}/approve",
            json={"approver_peer_id": "agent_linter", "reason": "Self approving"},
        )
        assert self_approve_res.status_code == 403
        assert "cannot self-approve" in self_approve_res.json()["detail"]

        # 3. Default query strictly hides unapproved proposed record
        query_safe = await client.get("/api/memory/tiered-consensus/records?scope_tier=team_consensus")
        assert query_safe.status_code == 200
        assert len(query_safe.json()) == 0

        # 4. Query with include_proposed=true shows the draft
        query_drafts = await client.get(
            "/api/memory/tiered-consensus/records?scope_tier=team_consensus&include_proposed=true"
        )
        assert query_drafts.status_code == 200
        assert len(query_drafts.json()) == 1

        # 5. Human administrator approves proposal
        approve_res = await client.post(
            f"/api/memory/tiered-consensus/records/{record_id}/approve",
            json={"approver_peer_id": "user_lead_architect", "reason": "Approved by architecture review"},
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "approved"

        # 6. Now default query returns the approved consensus
        query_after = await client.get("/api/memory/tiered-consensus/records?scope_tier=team_consensus")
        assert query_after.status_code == 200
        assert len(query_after.json()) == 1


@pytest.mark.asyncio
async def test_rejection_revocation_and_audit_api(test_app: FastAPI) -> None:
    """Validate rejecting a proposal, revoking consensus, and fetching audit logs via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Propose draft rule
        propose_res = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "team_consensus",
                "content": "Raw SQL injection testing in production",
                "owner_peer_id": "agent_tester",
            },
        )
        record_id = propose_res.json()["record_id"]

        # 2. Reject proposal
        reject_res = await client.post(
            f"/api/memory/tiered-consensus/records/{record_id}/reject",
            json={"approver_peer_id": "user_security_lead", "reason": "Severe security risk"},
        )
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "rejected"

        # 3. Propose personal rule and revoke it with supersession link
        personal_res = await client.post(
            "/api/memory/tiered-consensus/propose",
            json={
                "scope_tier": "personal",
                "content": "Legacy tab width = 4",
                "owner_peer_id": "user_developer",
            },
        )
        pers_id = personal_res.json()["record_id"]

        revoke_res = await client.post(
            f"/api/memory/tiered-consensus/records/{pers_id}/revoke",
            json={
                "operator_peer_id": "user_developer",
                "reason": "Standardized to 2 spaces",
                "superseded_by": "mem_tier_spaces_001",
            },
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "revoked"
        assert revoke_res.json()["superseded_by"] == "mem_tier_spaces_001"

        # 4. Fetch audit trail for the revoked record
        audit_res = await client.get(f"/api/memory/tiered-consensus/records/{pers_id}/audits")
        assert audit_res.status_code == 200
        audits = audit_res.json()
        assert len(audits) >= 2
        actions = [a["action"] for a in audits]
        assert "propose" in actions
        assert "revoke" in actions
