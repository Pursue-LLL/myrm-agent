"""
[INPUT]
- collections.abc (Generator)
- pytest
- fastapi (FastAPI)
- starlette.testclient (TestClient)
- app.api.agents.infra_quota_router (router, get_infra_quota_service)
- app.services.agent.infra_quota_service (InfraQuotaService)

[OUTPUT]
- test_get_infra_quota_overview_api: 测试四维基础设施配额概览获取与 Doctor 建议
- test_quota_check_and_fail_closed_guard_api: 测试自主申请准入门禁与超限 Fail-Closed 拦截
- test_quota_consume_and_status_escalation_api: 测试资源占用流转与健康状态动态跃迁
- test_update_quota_limits_api: 测试配额上限动态调整与即时生效

[POS]
Server 业务层每用户多 Agent 基础设施配额治理 REST API 自动化测试套件（Topic 12 · 第 16 项）。
基于隔离 TestClient 验证四大维度配额、准入门禁拦截、状态机跃迁与上限更新。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.infra_quota_router import (
    get_infra_quota_service,
)
from app.api.agents.infra_quota_router import (
    router as infra_quota_router,
)
from app.services.agent.infra_quota_service import InfraQuotaService


@pytest.fixture
def quota_client() -> Generator[TestClient, None, None]:
    """提供纯净隔离的 TestClient fixture 挂载 infra_quota_router。"""
    service = InfraQuotaService()

    test_app = FastAPI()
    test_app.include_router(infra_quota_router, prefix="/api/agents")
    test_app.dependency_overrides[get_infra_quota_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_get_infra_quota_overview_api(quota_client: TestClient) -> None:
    """测试获取基础设施配额概览。"""
    res = quota_client.get("/api/agents/infra-quota/overview?user_id=u_alpha")
    assert res.status_code == 200
    data = res.json()

    assert data["user_id"] == "u_alpha"
    assert len(data["quotas"]) == 4

    types = [q["resource_type"] for q in data["quotas"]]
    assert "active_agents" in types
    assert "ephemeral_dbs" in types
    assert "concurrent_sandboxes" in types
    assert "volume_storage_gb" in types

    assert len(data["doctor_recommendations"]) > 0
    assert "当前多 Agent 基础设施各维度配额充裕" in data["doctor_recommendations"][0]


def test_quota_check_and_fail_closed_guard_api(quota_client: TestClient) -> None:
    """测试自助 Provision 资源准入门禁 (Fail-Closed 判定)。"""
    # 1. 合规范围内的申请
    pass_res = quota_client.post(
        "/api/agents/infra-quota/check?user_id=u_beta",
        json={"resource_type": "active_agents", "requested_amount": 3.0},
    )
    assert pass_res.status_code == 200
    pass_data = pass_res.json()
    assert pass_data["allowed"] is True
    assert pass_data["remaining_after"] == 17.0
    assert pass_data["rejection_reason"] is None

    # 2. 超额申请：Fail-Closed 拦截
    deny_res = quota_client.post(
        "/api/agents/infra-quota/check?user_id=u_beta",
        json={"resource_type": "active_agents", "requested_amount": 25.0},
    )
    assert deny_res.status_code == 200
    deny_data = deny_res.json()
    assert deny_data["allowed"] is False
    assert deny_data["remaining_after"] == 0.0
    assert "基础设施配额不足" in deny_data["rejection_reason"]
    assert len(deny_data["remediation_steps"]) > 0


def test_quota_consume_and_status_escalation_api(quota_client: TestClient) -> None:
    """测试用量变更与健康状态由 normal -> critical 跃迁。"""
    user = "u_gamma"

    # 消耗 46 GB 卷空间 (上限 50 GB, 占比 92%)
    c_res = quota_client.post(
        f"/api/agents/infra-quota/consume?user_id={user}",
        json={"resource_type": "volume_storage_gb", "delta_amount": 46.0},
    )
    assert c_res.status_code == 200
    assert c_res.json()["updated_used"] == 46.0

    # 再次查询概览
    overview_res = quota_client.get(f"/api/agents/infra-quota/overview?user_id={user}")
    assert overview_res.status_code == 200
    overview_data = overview_res.json()

    vol_quota = next(q for q in overview_data["quotas"] if q["resource_type"] == "volume_storage_gb")
    assert vol_quota["used"] == 46.0
    assert vol_quota["usage_pct"] == 92.0
    assert vol_quota["status"] == "critical"

    # 验证 Doctor 智能调优建议触发
    rec_text = " ".join(overview_data["doctor_recommendations"])
    assert "持久 Volume 磁盘已占用" in rec_text
    assert "建议清空历史构建临时缓存" in rec_text


def test_update_quota_limits_api(quota_client: TestClient) -> None:
    """测试调整配额上限。"""
    user = "u_delta"
    update_payload = {
        "user_id": user,
        "concurrent_sandboxes_limit": 12.0,
        "volume_storage_gb_limit": 100.0,
    }
    put_res = quota_client.put("/api/agents/infra-quota/limits", json=update_payload)
    assert put_res.status_code == 200
    data = put_res.json()

    sandbox_quota = next(q for q in data["quotas"] if q["resource_type"] == "concurrent_sandboxes")
    assert sandbox_quota["limit"] == 12.0

    vol_quota = next(q for q in data["quotas"] if q["resource_type"] == "volume_storage_gb")
    assert vol_quota["limit"] == 100.0
