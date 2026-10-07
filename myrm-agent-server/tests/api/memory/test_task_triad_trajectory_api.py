"""Integration tests for Task Triad Trajectory and Anti-Loop Execution Blackbox API endpoints.

[POS]
Server layer integration test suite for Topic 01 Item 86.
Tests milestone logging, dead-end failed attempt recording, in-flight user steering capture,
action prohibition checking, and pre-prompt anti-loop snapshot generation.

[INPUT]
- FastAPI AsyncClient & test_app
- app.api.memory.task_triad_trajectory_router
- app.services.memory.task_triad_trajectory_service

[OUTPUT]
- Comprehensive tests validating HTTP contracts and business logic.
"""

from __future__ import annotations

import tempfile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.services.memory.task_triad_trajectory_service as service_module
from app.api.memory.task_triad_trajectory_router import (
    router as task_triad_trajectory_router,
)
from app.services.memory.task_triad_trajectory_service import (
    TaskTriadTrajectoryService,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting the triad trajectory router."""
    api_app = FastAPI()
    api_app.include_router(task_triad_trajectory_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset service instance with a clean temporary directory for each test."""
    temp_dir = tempfile.mkdtemp()
    service_module._service_instance = TaskTriadTrajectoryService(persistence_dir=temp_dir)


@pytest.mark.asyncio
async def test_record_milestone_endpoint(test_app: FastAPI) -> None:
    """Verify recording of a verified milestone via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "task_id": "task_audit_01",
            "session_id": "sess_audit",
            "initial_goal": "执行系统安全审计与漏洞修复",
            "step_index": 1,
            "title": "完成端口暴露扫描",
            "verified_output_summary": "发现 8080 和 9000 端口处于监听状态",
            "description": "基于 nmap 扫描本地环回接口",
            "artifacts_produced": ["audit_ports.log"],
        }
        resp = await client.post("/api/memory/triad-trajectory/milestone", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["step_index"] == 1
        assert data["title"] == "完成端口暴露扫描"
        assert "audit_ports.log" in data["artifacts_produced"]


@pytest.mark.asyncio
async def test_record_failed_attempt_and_check_action_endpoint(test_app: FastAPI) -> None:
    """Verify recording of dead ends and prohibition checking via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Record dead-end failed attempt
        failed_payload = {
            "task_id": "task_audit_02",
            "session_id": "sess_audit",
            "initial_goal": "重构数据库连接池",
            "step_index": 2,
            "action_attempted": "npm install mysql2",
            "error_type": "DriverMismatch",
            "error_summary": "当前环境为 PostgreSQL，不支持 mysql2",
            "dead_end_pattern": "mysql2",
            "prohibited_rule": "严禁在此项目中安装 mysql 驱动，必须使用 pg",
            "lessons_learned": "检查 package.json 确定主数据库为 postgres",
        }
        resp_fail = await client.post("/api/memory/triad-trajectory/failed-attempt", json=failed_payload)
        assert resp_fail.status_code == 201
        assert resp_fail.json()["dead_end_pattern"] == "mysql2"

        # 2. Check prohibited action
        check_payload_blocked = {
            "task_id": "task_audit_02",
            "action_text": "npm install mysql2 --save",
        }
        resp_check = await client.post("/api/memory/triad-trajectory/check-action", json=check_payload_blocked)
        assert resp_check.status_code == 200
        check_data = resp_check.json()
        assert check_data["is_prohibited"] is True
        assert "严禁在此项目中安装 mysql" in check_data["matched_rule"]
        assert check_data["matched_pattern"] == "mysql2"

        # 3. Check safe action
        check_payload_safe = {
            "task_id": "task_audit_02",
            "action_text": "npm install pg @types/pg",
        }
        resp_safe = await client.post("/api/memory/triad-trajectory/check-action", json=check_payload_safe)
        assert resp_safe.status_code == 200
        assert resp_safe.json()["is_prohibited"] is False


@pytest.mark.asyncio
async def test_record_user_steering_and_get_snapshot_endpoint(test_app: FastAPI) -> None:
    """Verify recording of user steerings and synthesis of pre-prompt snapshot."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        task_id = "task_refactor_03"

        # 1. Add milestone
        await client.post(
            "/api/memory/triad-trajectory/milestone",
            json={
                "task_id": task_id,
                "session_id": "sess_refactor",
                "initial_goal": "前端代码组件化改造",
                "step_index": 1,
                "title": "抽取通用 Card 基础组件",
                "verified_output_summary": "Card 组件单元测试 8 项全绿",
            },
        )

        # 2. Add failed attempt
        await client.post(
            "/api/memory/triad-trajectory/failed-attempt",
            json={
                "task_id": task_id,
                "session_id": "sess_refactor",
                "initial_goal": "前端代码组件化改造",
                "step_index": 2,
                "action_attempted": "import { Any } from 'legacy-types'",
                "error_type": "LintError",
                "error_summary": "严禁使用 Any 类型",
                "dead_end_pattern": "legacy-types",
                "prohibited_rule": "严禁导入 legacy-types 中的 Any",
            },
        )

        # 3. Add user in-flight steering
        steering_payload = {
            "task_id": task_id,
            "session_id": "sess_refactor",
            "initial_goal": "前端代码组件化改造",
            "turn_index": 4,
            "instruction_raw": "单文件代码行数严格控制在 400 行以内！",
            "distilled_constraint": "单文件行数不超过 400 行",
            "scope": "global",
        }
        resp_st = await client.post("/api/memory/triad-trajectory/steering", json=steering_payload)
        assert resp_st.status_code == 201
        assert resp_st.json()["distilled_constraint"] == "单文件行数不超过 400 行"

        # 4. Get anti-loop pre-prompt snapshot
        resp_snap = await client.get(
            f"/api/memory/triad-trajectory/{task_id}/anti-loop-snapshot?max_tokens=200"
        )
        assert resp_snap.status_code == 200
        snap_data = resp_snap.json()
        assert snap_data["task_id"] == task_id
        assert snap_data["latest_milestone_title"] == "抽取通用 Card 基础组件"
        assert "<task_triad_blackbox" in snap_data["formatted_prompt_block"]
        assert "单文件行数不超过 400 行" in snap_data["formatted_prompt_block"]


@pytest.mark.asyncio
async def test_get_blackbox_endpoint_and_404(test_app: FastAPI) -> None:
    """Verify full trajectory blackbox endpoint retrieval and 404 behavior."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existing task 404
        resp_404 = await client.get("/api/memory/triad-trajectory/task_nonexistent_99/blackbox")
        assert resp_404.status_code == 404

        # Existing task
        task_id = "task_blackbox_04"
        await client.post(
            "/api/memory/triad-trajectory/milestone",
            json={
                "task_id": task_id,
                "session_id": "sess_bb",
                "initial_goal": "构建沙箱环境",
                "step_index": 1,
                "title": "初始化 Dockerfile",
                "verified_output_summary": "镜像构建成功",
            },
        )

        resp_bb = await client.get(f"/api/memory/triad-trajectory/{task_id}/blackbox")
        assert resp_bb.status_code == 200
        bb_data = resp_bb.json()
        assert bb_data["task_id"] == task_id
        assert bb_data["status"] == "running"
        assert len(bb_data["milestones"]) == 1
