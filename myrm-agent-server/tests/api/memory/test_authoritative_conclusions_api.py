# [POS]: tests/api/memory/test_authoritative_conclusions_api.py
# [INPUT]: app.api.memory.authoritative_conclusions_router, FastAPI app
# [OUTPUT]: Integration API tests for Explicit Authoritative Conclusions Suite (Item 111)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.authoritative_conclusions_router import (
    router as authoritative_conclusions_router,
)
from app.services.memory.authoritative_conclusions_service import (
    AuthoritativeConclusionsService,
    get_authoritative_conclusions_service,
)


@pytest.fixture
def isolated_service() -> AuthoritativeConclusionsService:
    """Provides an isolated in-memory AuthoritativeConclusionsService instance."""
    return AuthoritativeConclusionsService()


@pytest.fixture
def test_app(isolated_service: AuthoritativeConclusionsService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(authoritative_conclusions_router, prefix="/api/memory")
    app.dependency_overrides[get_authoritative_conclusions_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_write_and_list_conclusions_api(test_app: FastAPI) -> None:
    """Validate declaring and querying authoritative conclusions via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Declare confirmed conclusion
        create_res = await client.post(
            "/api/memory/conclusions",
            json={
                "content": "代码质量红线: 单文件行数严格不超过 400 行",
                "peer_id": "user_architect",
                "scope_tag": "architecture",
                "auto_confirm": True,
                "rationale": "High maintainability mandate",
            },
        )
        assert create_res.status_code == 201
        data = create_res.json()
        assert data["content"] == "代码质量红线: 单文件行数严格不超过 400 行"
        assert data["status"] == "confirmed"
        cid = data["conclusion_id"]

        # 2. Get single conclusion
        get_res = await client.get(f"/api/memory/conclusions/{cid}")
        assert get_res.status_code == 200
        assert get_res.json()["peer_id"] == "user_architect"

        # 3. List conclusions
        list_res = await client.get("/api/memory/conclusions?scope_tag=architecture")
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) >= 1
        assert any(item["conclusion_id"] == cid for item in items)

        # 4. Keyword search
        kw_res = await client.get("/api/memory/conclusions?keyword=400")
        assert kw_res.status_code == 200
        assert len(kw_res.json()) >= 1


@pytest.mark.asyncio
async def test_deprecate_and_audit_history_api(test_app: FastAPI) -> None:
    """Validate conclusion deprecation transition and immutable audit logs."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Prepopulate conclusion
        create_res = await client.post(
            "/api/memory/conclusions",
            json={
                "content": "使用旧版 REST API v1 作为通信协议",
                "peer_id": "user_lead",
                "scope_tag": "legacy",
            },
        )
        cid = create_res.json()["conclusion_id"]

        # 1. Deprecate conclusion
        dep_res = await client.put(
            f"/api/memory/conclusions/{cid}/deprecate",
            json={
                "operator_peer_id": "user_lead",
                "rationale": "Upgraded to REST API v2",
            },
        )
        assert dep_res.status_code == 200
        assert dep_res.json()["status"] == "deprecated"
        assert dep_res.json()["deprecated_at"] is not None

        # 2. Query audit ledger
        audit_res = await client.get(f"/api/memory/conclusions/{cid}/audits")
        assert audit_res.status_code == 200
        audits = audit_res.json()
        assert len(audits) == 2  # 1 write, 1 deprecate
        assert audits[0]["action"] == "write"
        assert audits[1]["action"] == "deprecate"
        assert audits[1]["previous_status"] == "confirmed"
        assert audits[1]["new_status"] == "deprecated"


@pytest.mark.asyncio
async def test_delete_conclusion_physical_erasure_api(test_app: FastAPI) -> None:
    """Validate physical deletion for PII/policy compliance via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Prepopulate conclusion
        create_res = await client.post(
            "/api/memory/conclusions",
            json={
                "content": "临时测试敏感凭证结论",
                "peer_id": "agent_worker",
                "scope_tag": "test",
            },
        )
        cid = create_res.json()["conclusion_id"]

        # 1. Delete conclusion
        del_res = await client.request(
            "DELETE",
            f"/api/memory/conclusions/{cid}",
            json={
                "operator_peer_id": "security_admin",
                "rationale": "GDPR compliance purge",
            },
        )
        assert del_res.status_code == 204

        # 2. Verify subsequent get returns 404
        get_res = await client.get(f"/api/memory/conclusions/{cid}")
        assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_anti_dilution_anchor_projection_api(test_app: FastAPI) -> None:
    """Validate prompt context anchor projection generation via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Prepopulate active confirmed conclusion
        await client.post(
            "/api/memory/conclusions",
            json={
                "content": "所有业务服务必须遵循单例依赖注入 get_xxx_service()",
                "peer_id": "user_architect",
                "scope_tag": "architecture",
            },
        )

        # Retrieve anchor projection
        proj_res = await client.get("/api/memory/conclusions/anchor/projection")
        assert proj_res.status_code == 200
        proj = proj_res.json()
        assert proj["total_active_conclusions"] >= 1
        assert proj["token_estimate"] > 0
        assert "[AUTHORITATIVE ARCHITECTURAL & BUSINESS CONCLUSIONS]" in proj["formatted_prompt_block"]
        assert "所有业务服务必须遵循单例依赖注入" in proj["formatted_prompt_block"]
