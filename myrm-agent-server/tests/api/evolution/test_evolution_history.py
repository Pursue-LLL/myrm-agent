"""
[INPUT]
- app.api.skills.evolution.history (POS: evolution 历史记录接口层)
- app.services.skills.evolution_reviews (POS: evolution 审核生命周期服务)
[OUTPUT]
- GET /history whitelist filter tests
[POS]
验证 GET /evolution/history 端点的白名单状态过滤逻辑：仅返回 APPROVED/REJECTED 记录。
"""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="evolution")
from app.services.skills.evolution_reviews import (
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    approve_evolution_review_record,
    create_evolution_review_record,
    reject_evolution_review_record,
)


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _skill_path() -> str:
    return f"/tmp/test_skill_{uuid.uuid4().hex}.md"


async def _create_record(
    *,
    growth_status: EvolutionGrowthStatus = EvolutionGrowthStatus.PENDING_REVIEW,
    approval_status: str = "PENDING",
    skill_path: str | None = None,
) -> tuple[EvolutionReviewRecord, str]:
    path = skill_path or _skill_path()
    record = await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id=f"skill_{uuid.uuid4().hex[:8]}",
        skill_name="test_skill",
        skill_path=path,
        evolution_type="fix",
        reason="Test reason",
        original_content="def foo(): pass",
        evolved_content="def foo(): return 1",
        confidence=0.8,
        test_passed=True,
        task_context="history test",
        growth_status=growth_status,
        approval_status=approval_status,
    )
    return record, path


@pytest.fixture
async def approved_record():
    path = _skill_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("def foo(): pass")

    record, _ = await _create_record(skill_path=path)
    approved = await approve_evolution_review_record(record.id)
    yield approved
    for p in (path, f"{path}.bak"):
        if os.path.exists(p):
            os.remove(p)


@pytest.fixture
async def rejected_record():
    record, path = await _create_record()
    rejected = await reject_evolution_review_record(record.id)
    yield rejected
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
async def failed_scan_record():
    record, path = await _create_record(
        growth_status=EvolutionGrowthStatus.FAILED_SCAN,
    )
    yield record
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
async def pending_record():
    record, path = await _create_record()
    yield record
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_history_returns_approved_records(
    async_client: AsyncClient,
    approved_record: EvolutionReviewRecord,
) -> None:
    response = await async_client.get("/api/v1/evolution/history")
    assert response.status_code == 200
    data = response.json()
    item_ids = [item["id"] for item in data["items"]]
    assert approved_record.id in item_ids


@pytest.mark.asyncio
async def test_history_returns_rejected_records(
    async_client: AsyncClient,
    rejected_record: EvolutionReviewRecord,
) -> None:
    response = await async_client.get("/api/v1/evolution/history")
    assert response.status_code == 200
    data = response.json()
    item_ids = [item["id"] for item in data["items"]]
    assert rejected_record.id in item_ids


@pytest.mark.asyncio
async def test_history_excludes_failed_scan(
    async_client: AsyncClient,
    failed_scan_record: EvolutionReviewRecord,
) -> None:
    """FAILED_SCAN records must NOT appear in history (whitelist filter)."""
    response = await async_client.get("/api/v1/evolution/history")
    assert response.status_code == 200
    data = response.json()
    item_ids = [item["id"] for item in data["items"]]
    assert failed_scan_record.id not in item_ids


@pytest.mark.asyncio
async def test_history_excludes_pending(
    async_client: AsyncClient,
    pending_record: EvolutionReviewRecord,
) -> None:
    """PENDING_REVIEW records must NOT appear in history."""
    response = await async_client.get("/api/v1/evolution/history")
    assert response.status_code == 200
    data = response.json()
    item_ids = [item["id"] for item in data["items"]]
    assert pending_record.id not in item_ids


@pytest.mark.asyncio
async def test_history_status_values(
    async_client: AsyncClient,
    approved_record: EvolutionReviewRecord,
    rejected_record: EvolutionReviewRecord,
) -> None:
    """Verify serialized status values match frontend type expectations."""
    response = await async_client.get("/api/v1/evolution/history")
    assert response.status_code == 200
    data = response.json()
    statuses = {item["status"] for item in data["items"]}
    assert statuses <= {"approved", "rejected", "rolled_back"}


@pytest.mark.asyncio
async def test_history_limit_param(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/evolution/history?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 5


@pytest.mark.asyncio
async def test_history_record_fields(
    async_client: AsyncClient,
    approved_record: EvolutionReviewRecord,
) -> None:
    response = await async_client.get("/api/v1/evolution/history")
    assert response.status_code == 200
    data = response.json()
    item = next((i for i in data["items"] if i["id"] == approved_record.id), None)
    assert item is not None
    expected_keys = {
        "id", "skill_id", "skill_name", "evolution_type", "reason",
        "original_content", "evolved_content", "confidence", "test_passed",
        "status", "created_at", "resolved_at",
    }
    assert expected_keys <= set(item.keys())
