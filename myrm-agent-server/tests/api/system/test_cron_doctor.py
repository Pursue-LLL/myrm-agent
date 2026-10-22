"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.cron_doctor_api::router

[OUTPUT]:
- Pytest test cases verifying cron fleet health inspection across the 6 gates and surgical quick-fix repair APIs.

[POS]:
tests/api/system/test_cron_doctor.py — Cron 自动化任务舰队全景健康体检与外科手术式修复 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import os
import tempfile

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.cron_doctor_api import router as cron_doctor_router

test_app = FastAPI()
test_app.include_router(cron_doctor_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_cron_doctor_default_fleet_scan(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post("/api/v1/system/cron/doctor")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_jobs"] >= 5
    assert data["is_fleet_healthy"] is False
    assert data["issues_count"] >= 3

    categories = [i["category"] for i in data["issues"]]
    assert "EXECUTION_FAILED" in categories
    assert "DELIVERY_UNVERIFIED" in categories
    assert "SCHEDULE_OVERDUE" in categories
    assert "WORKDIR_NOT_FOUND" in categories


@pytest.mark.asyncio
async def test_cron_doctor_custom_targets_all_healthy(async_client: httpx.AsyncClient) -> None:
    valid_dir = tempfile.gettempdir()
    custom_targets = {
        "targets": [
            {
                "job_id": "cron-valid-1",
                "job_name": "Healthy Sync Job",
                "enabled": True,
                "last_run_status": "success",
                "last_delivery_status": "delivered",
                "delivery_receipt_verified": True,
                "next_run_at": 9999999999.0,
                "workdir_path": valid_dir,
            },
            {
                "job_id": "cron-valid-2",
                "job_name": "Healthy Internal Job",
                "enabled": True,
                "last_run_status": "success",
                "delivery_receipt_verified": True,
                "next_run_at": 9999999999.0,
            },
        ]
    }
    resp = await async_client.post("/api/v1/system/cron/doctor", json=custom_targets)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_jobs"] == 2
    assert data["healthy_jobs_count"] == 2
    assert data["issues_count"] == 0
    assert data["is_fleet_healthy"] is True
    assert len(data["issues"]) == 0


@pytest.mark.asyncio
async def test_quick_fix_workdir_and_schedule_remediations(async_client: httpx.AsyncClient) -> None:
    job_id = "cron-test-remediate"

    # 1. Quick-fix for missing workdir
    target_fix_dir = os.path.join(tempfile.gettempdir(), "test_quick_fix_dir_99")
    resp_dir = await async_client.post(
        f"/api/v1/system/cron/{job_id}/quick-fix",
        json={"issue_category": "WORKDIR_NOT_FOUND", "remediation_param": target_fix_dir},
    )
    assert resp_dir.status_code == 200
    dir_data = resp_dir.json()
    assert dir_data["status"] == "REMEDIATED"
    assert "已自动创建并初始化专属工作区目录" in dir_data["message"]
    assert os.path.exists(target_fix_dir)

    # 2. Quick-fix for overdue schedule
    resp_sched = await async_client.post(
        f"/api/v1/system/cron/{job_id}/quick-fix",
        json={"issue_category": "SCHEDULE_OVERDUE"},
    )
    assert resp_sched.status_code == 200
    sched_data = resp_sched.json()
    assert sched_data["status"] == "REMEDIATED"
    assert "已重置任务下次调度触发时间" in sched_data["message"]
