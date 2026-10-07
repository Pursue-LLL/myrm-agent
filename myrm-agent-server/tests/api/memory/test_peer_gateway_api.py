# [POS]: tests/api/memory/test_peer_gateway_api.py
# [INPUT]: app.api.memory.peer_gateway_router, FastAPI app
# [OUTPUT]: Integration API tests for Multi-Channel Peer Gateway Suite (Item 113)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.peer_gateway_router import (
    router as peer_gateway_router,
)
from app.services.memory.peer_gateway_service import (
    PeerGatewayService,
    get_peer_gateway_service,
)


@pytest.fixture
def isolated_service() -> PeerGatewayService:
    """Provides an isolated in-memory PeerGatewayService instance."""
    return PeerGatewayService()


@pytest.fixture
def test_app(isolated_service: PeerGatewayService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(peer_gateway_router, prefix="/api/memory")
    app.dependency_overrides[get_peer_gateway_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_resolve_peer_and_alias_api(test_app: FastAPI) -> None:
    """Validate resolving external channel identities, registering aliases, and querying alias tables."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register explicit alias mapping for Feishu
        reg_res = await client.post(
            "/api/memory/peer-gateway/aliases",
            json={"channel_key": "feishu:ou_alex_001", "canonical_peer_id": "peer_alex_canonical"},
        )
        assert reg_res.status_code == 200
        aliases = reg_res.json()
        assert aliases["feishu:ou_alex_001"] == "peer_alex_canonical"

        # 2. Resolve known aliased user
        resolve_aliased = await client.post(
            "/api/memory/peer-gateway/resolve",
            json={"channel_type": "feishu", "raw_channel_id": "ou_alex_001"},
        )
        assert resolve_aliased.status_code == 200
        data_aliased = resolve_aliased.json()
        assert data_aliased["canonical_peer_id"] == "peer_alex_canonical"
        assert data_aliased["alias_matched"] is True

        # 3. Resolve unknown user falling back to adaptive hash escalation
        resolve_unknown = await client.post(
            "/api/memory/peer-gateway/resolve",
            json={"channel_type": "telegram", "raw_channel_id": "tg_user_9988"},
        )
        assert resolve_unknown.status_code == 200
        data_unknown = resolve_unknown.json()
        assert data_unknown["canonical_peer_id"].startswith("peer_telegram_tg_user_9988_")
        assert data_unknown["alias_matched"] is False

        # 4. Get all aliases
        list_res = await client.get("/api/memory/peer-gateway/aliases")
        assert list_res.status_code == 200
        assert "feishu:ou_alex_001" in list_res.json()


@pytest.mark.asyncio
async def test_boundary_verification_and_hash_escalation_api(test_app: FastAPI) -> None:
    """Validate boundary fences preventing cross-peer contamination and hash escalation logic."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Self memory access permitted
        self_check = await client.post(
            "/api/memory/peer-gateway/verify-boundary",
            json={"session_peer_id": "peer_alex", "target_peer_id": "peer_alex"},
        )
        assert self_check.status_code == 200
        assert self_check.json()["allowed"] is True
        assert self_check.json()["violation_reason"] is None

        # 2. Cross-peer unauthorized memory access blocked
        cross_check = await client.post(
            "/api/memory/peer-gateway/verify-boundary",
            json={"session_peer_id": "peer_alex", "target_peer_id": "peer_bob_private"},
        )
        assert cross_check.status_code == 200
        cross_data = cross_check.json()
        assert cross_data["allowed"] is False
        assert "Cross-peer contamination blocked" in cross_data["violation_reason"]

        # 3. Hash escalation without collision
        escalate_res_1 = await client.post(
            "/api/memory/peer-gateway/escalate-hash",
            json={"raw_id": "user_device_abc", "existing_peers": []},
        )
        assert escalate_res_1.status_code == 200
        esc_data_1 = escalate_res_1.json()
        assert esc_data_1["was_escalated"] is False
        first_id = esc_data_1["escalated_id"]

        # 4. Hash escalation with collision triggers length expansion
        escalate_res_2 = await client.post(
            "/api/memory/peer-gateway/escalate-hash",
            json={"raw_id": "user_device_abc", "existing_peers": [first_id]},
        )
        assert escalate_res_2.status_code == 200
        esc_data_2 = escalate_res_2.json()
        assert esc_data_2["was_escalated"] is True
        assert esc_data_2["escalated_id"] != first_id
