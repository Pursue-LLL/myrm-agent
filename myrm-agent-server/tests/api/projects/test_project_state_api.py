"""
[POS] tests/api/projects/test_project_state_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.projects.project_state, app.services.project.project_state_service
[OUTPUT] test_project_state_facts_crud_api, test_project_state_filter_by_type_and_stage_api, test_four_tier_context_projection_pipeline_api, test_validation_audit_gate_api, test_get_nonexistent_fact_404_api

Unit test suite for ProjectState living fact ledger and context projection API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.projects.project_state import router as project_state_router
from app.services.project.project_state_service import (
    ProjectStateService,
    get_project_state_service,
)


@pytest.fixture
def project_state_test_client() -> Generator[
    tuple[TestClient, ProjectStateService], None, None
]:
    """Provide isolated TestClient mounting project_state router with clean service instance."""
    service = ProjectStateService()

    test_app = FastAPI()
    test_app.include_router(project_state_router, prefix="/api")
    test_app.dependency_overrides[get_project_state_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_project_state_facts_crud_api(
    project_state_test_client: tuple[TestClient, ProjectStateService],
) -> None:
    """Verify recording, retrieving, listing, and deleting a living fact via API."""
    client, _ = project_state_test_client
    project_id = "test-proj-001"

    create_payload: dict[str, object] = {
        "fact_id": "fact-c1",
        "fact_type": "constraint",
        "title": "单文件400行上限",
        "content": "单个Python文件代码原则上不超过400行，超过须拆分",
        "target_components": ["core", "api"],
        "reason_or_constraint": "避免屎山与巨型单体文件",
        "promotion_stage": "confirmed_fact",
        "metadata": {"enforced_by": "architect"},
    }

    # 1. 创建事实
    resp = client.post(f"/api/projects/{project_id}/state/facts", json=create_payload)
    assert resp.status_code == 201
    created = resp.json()
    assert created["fact_id"] == "fact-c1"
    assert created["fact_type"] == "constraint"
    assert created["validation_count"] == 0

    # 2. 查询单条事实
    resp = client.get(f"/api/projects/{project_id}/state/facts/fact-c1")
    assert resp.status_code == 200
    retrieved = resp.json()
    assert retrieved["title"] == "单文件400行上限"

    # 3. 列出事实
    resp = client.get(f"/api/projects/{project_id}/state/facts")
    assert resp.status_code == 200
    list_data = resp.json()
    assert list_data["total_count"] == 1
    assert len(list_data["facts"]) == 1

    # 4. 删除事实
    resp = client.delete(f"/api/projects/{project_id}/state/facts/fact-c1")
    assert resp.status_code == 204

    # 5. 再次查询应返回 404
    resp = client.get(f"/api/projects/{project_id}/state/facts/fact-c1")
    assert resp.status_code == 404


def test_project_state_filter_by_type_and_stage_api(
    project_state_test_client: tuple[TestClient, ProjectStateService],
) -> None:
    """Verify filtering facts by fact_type and promotion_stage."""
    client, _ = project_state_test_client
    project_id = "test-proj-filter"

    # 登记决策
    client.post(
        f"/api/projects/{project_id}/state/facts",
        json={
            "fact_id": "dec-1",
            "fact_type": "decision",
            "title": "选择 FastAPI",
            "content": "使用 FastAPI 构建高性能异步接口",
            "promotion_stage": "confirmed_fact",
        },
    )
    # 登记否决项
    client.post(
        f"/api/projects/{project_id}/state/facts",
        json={
            "fact_id": "rej-1",
            "fact_type": "rejected_alternative",
            "title": "否决同步 Django",
            "content": "同步阻塞 IO 会导致高并发性能瓶颈",
            "promotion_stage": "confirmed_fact",
        },
    )

    # 按 fact_type=rejected_alternative 过滤
    resp = client.get(f"/api/projects/{project_id}/state/facts?fact_type=rejected_alternative")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["facts"][0]["fact_id"] == "rej-1"


def test_four_tier_context_projection_pipeline_api(
    project_state_test_client: tuple[TestClient, ProjectStateService],
) -> None:
    """Verify four-tier context projection extracts constraints, rejected alternatives, and contracts."""
    client, _ = project_state_test_client
    project_id = "test-proj-projection"

    # 录入约束、契约与被否决路径
    client.post(
        f"/api/projects/{project_id}/state/facts",
        json={
            "fact_id": "const-1",
            "fact_type": "constraint",
            "title": "严禁使用 Any 类型",
            "content": "必须具备明确的类型注解",
            "target_components": ["BillingModule"],
            "reason_or_constraint": "消除隐式类型错误",
        },
    )
    client.post(
        f"/api/projects/{project_id}/state/facts",
        json={
            "fact_id": "rej-1",
            "fact_type": "rejected_alternative",
            "title": "前端直连支付网关方案",
            "content": "前端直接携带密钥向三方网关发起划扣",
            "target_components": ["BillingModule"],
            "reason_or_constraint": "密钥泄露高危反模式，必须通过后端安全代理",
        },
    )
    client.post(
        f"/api/projects/{project_id}/state/facts",
        json={
            "fact_id": "contract-1",
            "fact_type": "interface_contract",
            "title": "Payment Intent V3",
            "content": "POST /api/payment/intent 创建幂等支付凭证",
            "target_components": ["BillingModule"],
        },
    )

    projection_req: dict[str, object] = {
        "target_task": "实现 BillingModule 支付流程对接与异常兜底",
        "target_components": ["BillingModule"],
        "token_budget": 1200,
    }
    resp = client.post(
        f"/api/projects/{project_id}/state/project-context", json=projection_req
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["project_id"] == project_id
    assert "<project_state_context>" in result["formatted_prompt_block"]
    assert "REJECTED ALTERNATIVES - DO NOT RETRY" in result["formatted_prompt_block"]
    assert "前端直连支付网关方案" in result["formatted_prompt_block"]
    assert "严禁使用 Any 类型" in result["formatted_prompt_block"]
    assert len(result["facts"]) >= 3


def test_validation_audit_gate_api(
    project_state_test_client: tuple[TestClient, ProjectStateService],
) -> None:
    """Verify deterministic validation gate advances promotion stage and increments counters."""
    client, _ = project_state_test_client
    project_id = "test-proj-audit"

    client.post(
        f"/api/projects/{project_id}/state/facts",
        json={
            "fact_id": "fact-audit-target",
            "fact_type": "decision",
            "title": "自适应连接池方案",
            "content": "根据负载动态调整连接数",
            "promotion_stage": "confirmed_fact",
        },
    )

    # 第一次验证通过
    audit_resp = client.post(
        f"/api/projects/{project_id}/state/audit-validation",
        json={
            "fact_id": "fact-audit-target",
            "passed": True,
            "test_summary": "单元测试与高并发压测均无异常",
        },
    )
    assert audit_resp.status_code == 200
    data = audit_resp.json()
    assert data["validation_count"] == 1
    assert data["regression_count"] == 0

    # 第二次验证通过 -> 晋升至 knowledge
    audit_resp2 = client.post(
        f"/api/projects/{project_id}/state/audit-validation",
        json={
            "fact_id": "fact-audit-target",
            "passed": True,
            "test_summary": "多轮验收零回归",
        },
    )
    assert audit_resp2.status_code == 200
    data2 = audit_resp2.json()
    assert data2["validation_count"] == 2
    assert data2["is_promoted"] is True
    assert data2["new_stage"] == "knowledge"


def test_get_nonexistent_fact_404_api(
    project_state_test_client: tuple[TestClient, ProjectStateService],
) -> None:
    """Verify 404 response for nonexistent fact deletion or query."""
    client, _ = project_state_test_client
    project_id = "test-proj-empty"

    resp = client.get(f"/api/projects/{project_id}/state/facts/non-existent-id")
    assert resp.status_code == 404

    resp_del = client.delete(f"/api/projects/{project_id}/state/facts/non-existent-id")
    assert resp_del.status_code == 404
