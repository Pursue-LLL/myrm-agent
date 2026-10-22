"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.delivery_dossier_api::router

[OUTPUT]:
- Pytest test cases verifying delivery evidence dossier archiving, retrieval by task ID, and stratified asset friction metrics.

[POS]:
tests/api/system/test_delivery_dossier_api.py — 跨智能体交付证据卷宗与资产摩擦度量 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.delivery_dossier_api import router as delivery_dossier_router

test_app = FastAPI()
test_app.include_router(delivery_dossier_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_archive_and_get_dossier_api(async_client: httpx.AsyncClient) -> None:
    payload = {
        "task_id": "task-dossier-01",
        "execution_mode": "MULTI_TURN_AGENT",
        "spec": {
            "task_goal": "实现双账本计量引擎与未知用量审计",
            "acceptance_criteria": ["双账本聚合", "单测 100% 绿灯"],
            "non_goals": ["无需对接三方计费 SaaS"],
        },
        "persona": {
            "agent_id": "agent-lead-01",
            "model_name": "claude-3-5-sonnet",
            "prompt_hash": "ph_test998877",
            "mounted_skills": ["bash", "file_edit"],
        },
        "tool_traces": [
            {
                "tool_name": "bash",
                "arguments_summary": "pytest tests/test_budget.py",
                "duration_ms": 320.0,
                "exit_code": 0,
                "error_message": None,
            }
        ],
        "verification": {
            "test_suite_exit_code": 0,
            "passed_tests_count": 3,
            "failed_tests_count": 0,
            "artifact_path": "myrm-agent-server/app/api/system/budget_api.py",
            "artifact_sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
            "verified_at": "2026-10-12T15:00:00Z",
        },
        "acceptance": "ACCEPTED",
        "total_tokens_consumed": 15_000,
        "wasted_friction_tokens": 200,
        "rework_count": 0,
    }

    # 1. 归档证据卷宗
    archive_resp = await async_client.post(
        "/api/v1/system/delivery-dossier/archive", json=payload
    )
    assert archive_resp.status_code == 200
    dossier_data = archive_resp.json()

    dossier_id = dossier_data["dossier_id"]
    assert dossier_id.startswith("dos_")
    assert len(dossier_data["dossier_checksum_sha256"]) == 64
    assert dossier_data["verification"]["test_suite_exit_code"] == 0
    assert dossier_data["acceptance"] == "ACCEPTED"

    # 2. 根据 dossier_id 获取
    get_resp = await async_client.get(f"/api/v1/system/delivery-dossier/{dossier_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["dossier_id"] == dossier_id

    # 3. 根据 task_id 获取
    by_task_resp = await async_client.get("/api/v1/system/delivery-dossier/by-task/task-dossier-01")
    assert by_task_resp.status_code == 200
    assert by_task_resp.json()["task_id"] == "task-dossier-01"

    # 4. 查询不存在的卷宗
    nf_resp = await async_client.get("/api/v1/system/delivery-dossier/dos_nonexistent")
    assert nf_resp.status_code == 404


@pytest.mark.asyncio
async def test_record_friction_trial_and_stratified_evaluation_api(
    async_client: httpx.AsyncClient,
) -> None:
    # 1. 针对 sonnet 注入 3 组高效优质样本
    for _ in range(3):
        t1 = await async_client.post(
            "/api/v1/system/delivery-dossier/record-friction-trial",
            json={
                "skill_id": "k8s_manifest_deploy",
                "model_name": "claude-3-5-sonnet",
                "execution_mode": "MULTI_TURN_AGENT",
                "accepted": True,
                "retries": 0,
                "rework": False,
                "wasted_tokens": 100,
                "baseline_tokens": 5000,
            },
        )
        assert t1.status_code == 200

    # 2. 针对 deepseek 注入 3 组摩擦严重样本
    for _ in range(3):
        t2 = await async_client.post(
            "/api/v1/system/delivery-dossier/record-friction-trial",
            json={
                "skill_id": "k8s_manifest_deploy",
                "model_name": "deepseek-chat",
                "execution_mode": "MULTI_TURN_AGENT",
                "accepted": False,
                "retries": 5,
                "rework": True,
                "wasted_tokens": 6000,
                "baseline_tokens": 5000,
            },
        )
        assert t2.status_code == 200

    # 3. 查验全量分层列表
    all_resp = await async_client.get("/api/v1/system/delivery-dossier/asset-friction/all")
    assert all_resp.status_code == 200
    metrics = all_resp.json()
    assert len(metrics) >= 2

    # 4. 单项评估 sonnet 与 deepseek
    sonnet_metric = await async_client.get(
        "/api/v1/system/delivery-dossier/asset-friction/k8s_manifest_deploy?model_name=claude-3-5-sonnet"
    )
    assert sonnet_metric.status_code == 200
    assert sonnet_metric.json()["health_tag"] == "CORE_EFFICIENT"
    assert sonnet_metric.json()["true_efficacy_rate_pct"] == 100.0

    deepseek_metric = await async_client.get(
        "/api/v1/system/delivery-dossier/asset-friction/k8s_manifest_deploy?model_name=deepseek-chat"
    )
    assert deepseek_metric.status_code == 200
    assert deepseek_metric.json()["health_tag"] == "FRICTION_ASSASSIN"
    assert deepseek_metric.json()["true_efficacy_rate_pct"] == 0.0
