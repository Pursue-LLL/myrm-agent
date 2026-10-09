"""[POS]: tests/api/memory/test_decisions_api.py
[INPUT]: FastAPI TestClient, tmp_path, and engineering decision endpoints.
[OUTPUT]: Pytest integration tests verifying staging, confirmation gate, lineage DAG, and priority recall.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import EngineeringDecisionStore

from app.api.memory.decisions import (
    get_decision_store,
)
from app.api.memory.decisions import (
    router as decisions_router,
)


@pytest.fixture
def isolated_store(tmp_path: Path) -> EngineeringDecisionStore:
    """Create isolated store instance backed by temporary test database."""
    test_db = tmp_path / "test_api_decisions.db"
    return EngineeringDecisionStore(db_path=test_db, auto_approve=False)


@pytest.fixture
def test_app(isolated_store: EngineeringDecisionStore) -> FastAPI:
    """Create FastAPI test application with injected isolated decision store."""
    api_app = FastAPI()
    api_app.include_router(decisions_router, prefix="/api/memory")
    api_app.dependency_overrides[get_decision_store] = lambda: isolated_store
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to the isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_decision_staging_and_confirmation_flow(client: AsyncClient) -> None:
    """Verify staging a decision candidate and approving it via confirmation gate."""
    # 1. Stage candidate
    stage_resp = await client.post(
        "/api/memory/decisions/stage",
        json={
            "session_id": "sess_api_01",
            "title": "鉴权机制定案",
            "text": "全面采用服务端 Session 状态化方案，废弃无状态 JWT",
            "rationale": "单机沙箱内聚安全与即时注销能力",
            "project_key": "proj_core",
        },
    )
    assert stage_resp.status_code == 200
    candidate = stage_resp.json()
    assert candidate["status"] == "pending"
    assert "id" in candidate
    cand_id = candidate["id"]

    # 2. Confirm candidate
    confirm_resp = await client.post(
        "/api/memory/decisions/confirm",
        json={"candidate_id": cand_id},
    )
    assert confirm_resp.status_code == 200
    decision = confirm_resp.json()
    assert decision["status"] == "active"
    assert decision["title"] == "鉴权机制定案"
    dec_id = decision["id"]

    # 3. List decisions
    list_resp = await client.get("/api/memory/decisions/list", params={"project_key": "proj_core"})
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == dec_id


@pytest.mark.asyncio
async def test_decision_supersession_lineage_and_recall(client: AsyncClient) -> None:
    """Verify active-to-superseded lineage transition and structured priority recall."""
    # 1. Create first decision directly
    d1_resp = await client.post(
        "/api/memory/decisions/direct",
        json={
            "title": "向量存储方案",
            "text": "使用外部 Docker Qdrant 实例",
            "rationale": "早期原型开发快速接入",
            "project_key": "proj_core",
        },
    )
    assert d1_resp.status_code == 200
    d1 = d1_resp.json()
    assert d1["status"] == "active"
    d1_id = d1["id"]

    # 2. Create second decision superseding the first
    d2_resp = await client.post(
        "/api/memory/decisions/direct",
        json={
            "title": "向量存储升级",
            "text": "升级为单文件嵌入式 sqlite-vec 零守护进程引擎",
            "rationale": "彻底根治 Docker 端口冲突与崩溃痛点，极致本地优先",
            "supersedes_id": d1_id,
            "project_key": "proj_core",
        },
    )
    assert d2_resp.status_code == 200
    d2 = d2_resp.json()
    assert d2["status"] == "active"
    assert d2["supersedes_id"] == d1_id
    d2_id = d2["id"]

    # 3. Verify old decision is now SUPERSEDED
    list_resp = await client.get("/api/memory/decisions/list", params={"project_key": "proj_core"})
    items = {item["id"]: item for item in list_resp.json()}
    assert items[d1_id]["status"] == "superseded"
    assert items[d1_id]["superseded_by"] == d2_id

    # 4. Query lineage
    lineage_resp = await client.get(f"/api/memory/decisions/lineage/{d2_id}")
    assert lineage_resp.status_code == 200
    chain = lineage_resp.json()
    assert len(chain) == 2
    assert chain[0]["id"] == d1_id
    assert chain[1]["id"] == d2_id

    # 5. Search priority recall
    search_resp = await client.post(
        "/api/memory/decisions/search_priority",
        json={
            "query": "请问我们系统的向量存储选型方案是什么？",
            "project_key": "proj_core",
            "limit": 5,
        },
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert len(search_data["hits"]) >= 1
    assert "生效架构决策与代际链" in search_data["prompt_block"]
    assert "元认知边界声明" in search_data["prompt_block"]


@pytest.mark.asyncio
async def test_rejection_and_noise_filtering(client: AsyncClient) -> None:
    """Verify rejection flow and system noise rejection."""
    # 1. Noise filtering rejection
    noise_resp = await client.post(
        "/api/memory/decisions/stage",
        json={
            "session_id": "sess_noise",
            "title": "系统提醒",
            "text": "<system-reminder> This is internal harness noise </system-reminder>",
        },
    )
    assert noise_resp.status_code == 400

    # 2. Reject candidate
    cand_resp = await client.post(
        "/api/memory/decisions/stage",
        json={
            "session_id": "sess_reject",
            "title": "临时提案",
            "text": "使用 Redis 缓存临时变量",
        },
    )
    assert cand_resp.status_code == 200
    cand_id = cand_resp.json()["id"]

    reject_resp = await client.post(
        "/api/memory/decisions/reject",
        json={"candidate_id": cand_id},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"
