"""[INPUT]
- app.api.agents.fleet_telemetry::router
- /api/v1/agents/fleet/diagnose
- /api/v1/agents/fleet/health-summary

[OUTPUT]
- test_get_fleet_health_summary
- test_diagnose_node_mock_offline
- test_diagnose_node_provider_quota_exhausted

[POS]
tests/api/agents/test_fleet_telemetry.py — 分布式机队六态遥测与配额诊断 API 端点单元测试。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agents.fleet_telemetry import router as fleet_telemetry_router

app = FastAPI()
app.include_router(fleet_telemetry_router, prefix="/api/v1/agents")
client = TestClient(app)

_DIAGNOSE_URL = "/api/v1/agents/fleet/diagnose"
_SUMMARY_URL = "/api/v1/agents/fleet/health-summary"


def test_get_fleet_health_summary() -> None:
    """获取机队健康概览，应返回 200 并包含完整的六态分布统计。"""
    response = client.get(_SUMMARY_URL)
    assert response.status_code == 200
    data = response.json()
    assert "total_nodes" in data
    assert "online_count" in data
    assert "offline_count" in data
    assert "provider_unavailable_count" in data
    assert "quota_healthy" in data
    assert isinstance(data["quota_healthy"], bool)


def test_diagnose_node_mock_offline() -> None:
    """探测离线主机应迅速归因为 offline 并返回针对性排障指导。"""
    payload = {
        "node_id": "test-node-off",
        "node_name": "Remote-Host-1",
        "host": "192.0.2.1",  # 保留未分配测试 IP
        "port": 9999,
    }

    # 模拟物理探测超时/失败
    with patch(
        "myrm_agent_harness.observability.diagnostics.fleet_telemetry.evaluator.default_physical_probe",
        new=AsyncMock(return_value=(False, "Connection timeout")),
    ):
        response = client.post(_DIAGNOSE_URL, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "test-node-off"
    assert data["state"] == "offline"
    assert "离线" in data["root_cause"] or "中断" in data["root_cause"]
    assert len(data["stages"]) == 1
    assert data["stages"][0]["stage"] == "physical_network"
    assert data["stages"][0]["passed"] is False


def test_diagnose_node_provider_quota_exhausted() -> None:
    """探测正常主机但模型 API 欠费时，应精准归因为 provider_unavailable。"""
    payload = {
        "node_id": "test-node-quota",
        "node_name": "Tony-Mac-Studio",
        "host": "127.0.0.1",
        "port": 8000,
        "provider_name": "Anthropic",
        "model_name": "claude-3-5-sonnet",
    }

    from myrm_agent_harness.observability.diagnostics.fleet_telemetry.evaluator import (
        FleetSixStateDiagnoser,
    )

    async def mock_phys(_h: str, _p: int) -> tuple[bool, str]:
        return True, "OK"

    async def mock_prov(_t: object) -> tuple[int, str]:
        return 402, "Your credit balance is too low"

    custom_diagnoser = FleetSixStateDiagnoser(
        physical_probe=mock_phys,
        provider_probe=mock_prov,
    )

    with patch(
        "app.api.agents.fleet_telemetry.FleetSixStateDiagnoser",
        return_value=custom_diagnoser,
    ):
        response = client.post(_DIAGNOSE_URL, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "test-node-quota"
    assert data["state"] == "provider_unavailable"
    assert "欠费停服" in data["root_cause"] or "耗尽" in data["root_cause"]
    assert "充值" in data["recommended_action"]
    assert len(data["stages"]) == 2
    assert data["stages"][1]["stage"] == "provider_quota"
    assert data["stages"][1]["passed"] is False
