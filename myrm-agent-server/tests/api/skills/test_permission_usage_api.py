"""Skill permission usage aggregation endpoint tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_db_session
from app.api.skills.permissions import router as permissions_router
from app.database.models import SkillPermissionUsageLog


def _make_log(
    permission: str,
    operation: str,
    allowed: bool,
    deny_reason: str | None = None,
    used_at_delta: timedelta = timedelta(hours=1),
) -> SkillPermissionUsageLog:
    return SkillPermissionUsageLog(
        id=0,
        user_id="test-user",
        skill_id="skill-test",
        permission=permission,
        operation=operation,
        allowed=allowed,
        deny_reason=deny_reason,
        used_at=datetime.now(UTC).replace(tzinfo=None) - used_at_delta,
    )


class _FakeSkill:
    name = "Test Skill"


def _override_db_session(logs: list[SkillPermissionUsageLog]):
    """构造覆盖 get_db_session 依赖的假 session（返回预置日志）。"""

    async def _factory() -> AsyncMock:
        session = AsyncMock()
        result = Mock()
        result.scalars.return_value.all.return_value = logs
        session.execute = AsyncMock(return_value=result)
        return session

    return _factory


@pytest.fixture
def usage_app() -> FastAPI:
    app = FastAPI()
    app.include_router(permissions_router, prefix="/api/v1/skills")
    return app


async def _fetch_usage(client: AsyncClient, days: int = 7) -> dict:
    response = await client.get(f"/api/v1/skills/skill-test/permissions/usage?days={days}")
    assert response.status_code == 200
    return response.json()


async def test_usage_groups_by_permission_and_counts(usage_app: FastAPI) -> None:
    logs = [
        _make_log("file_read", "read a.txt", True),
        _make_log("file_read", "read b.txt", False, "not granted"),
        _make_log("network_access", "GET https://example.com", True),
        _make_log("file_read", "read c.txt", True),
    ]
    usage_app.dependency_overrides[get_db_session] = _override_db_session(logs)
    transport = ASGITransport(app=usage_app)
    with patch(
        "app.api.skills.permissions.skills_service.get_skill",
        AsyncMock(return_value=_FakeSkill()),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = await _fetch_usage(client)

    assert payload["skill_id"] == "skill-test"
    assert payload["skill_name"] == "Test Skill"
    assert payload["total_operations"] == 4

    stats = {s["permission"]: s for s in payload["stats"]}
    assert stats["file_read"]["total_count"] == 3
    assert stats["file_read"]["allowed_count"] == 2
    assert stats["file_read"]["denied_count"] == 1
    assert stats["network_access"]["total_count"] == 1
    assert stats["network_access"]["allowed_count"] == 1
    assert stats["network_access"]["denied_count"] == 0


async def test_usage_caps_recent_operations_at_ten(usage_app: FastAPI) -> None:
    # 模拟 DB 按 used_at DESC 返回：最新在前（cmd 11 最新）
    logs = [_make_log("shell_exec", f"cmd {i}", True, used_at_delta=timedelta(hours=12 - i)) for i in range(11, -1, -1)]
    usage_app.dependency_overrides[get_db_session] = _override_db_session(logs)
    transport = ASGITransport(app=usage_app)
    with patch(
        "app.api.skills.permissions.skills_service.get_skill",
        AsyncMock(return_value=_FakeSkill()),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = await _fetch_usage(client)

    stats = payload["stats"]
    assert len(stats) == 1
    assert stats[0]["total_count"] == 12
    assert stats[0]["allowed_count"] == 12
    assert len(stats[0]["recent_operations"]) == 10
    # recent 保留最新 10 条
    assert stats[0]["recent_operations"][0]["operation"] == "cmd 11"
    recent_ops = [op["operation"] for op in stats[0]["recent_operations"]]
    assert "cmd 0" not in recent_ops
    assert "cmd 1" not in recent_ops


async def test_usage_deny_reason_and_recency_order(usage_app: FastAPI) -> None:
    # 模拟 DB 按 used_at DESC 返回：最新在前（write KEY 最新）
    logs = [
        _make_log("env_var_access", "write KEY", True, None, timedelta(hours=1)),
        _make_log("env_var_access", "read KEY", True, None, timedelta(hours=2)),
        _make_log("env_var_access", "read KEY", False, "not granted", timedelta(hours=3)),
    ]
    usage_app.dependency_overrides[get_db_session] = _override_db_session(logs)
    transport = ASGITransport(app=usage_app)
    with patch(
        "app.api.skills.permissions.skills_service.get_skill",
        AsyncMock(return_value=_FakeSkill()),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = await _fetch_usage(client)

    stats = payload["stats"]
    assert len(stats) == 1
    assert stats[0]["total_count"] == 3
    assert stats[0]["allowed_count"] == 2
    assert stats[0]["denied_count"] == 1

    recent = stats[0]["recent_operations"]
    assert len(recent) == 3
    # 按传入顺序保留（端点按 used_at desc 排序后取前 10）
    assert recent[0]["operation"] == "write KEY"
    assert recent[0]["deny_reason"] is None
    assert recent[2]["operation"] == "read KEY"
    assert recent[2]["deny_reason"] == "not granted"


async def test_usage_empty_logs(usage_app: FastAPI) -> None:
    usage_app.dependency_overrides[get_db_session] = _override_db_session([])
    transport = ASGITransport(app=usage_app)
    with patch(
        "app.api.skills.permissions.skills_service.get_skill",
        AsyncMock(return_value=_FakeSkill()),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = await _fetch_usage(client)

    assert payload["total_operations"] == 0
    assert payload["stats"] == []


async def test_usage_returns_404_for_unknown_skill(usage_app: FastAPI) -> None:
    transport = ASGITransport(app=usage_app)
    with patch(
        "app.api.skills.permissions.skills_service.get_skill",
        AsyncMock(return_value=None),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/skills/missing/permissions/usage")
    assert response.status_code == 404


async def test_usage_rejects_invalid_days(usage_app: FastAPI) -> None:
    """days 越界（0 / 366）返回 422。"""
    transport = ASGITransport(app=usage_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/skills/skill-test/permissions/usage?days=0")
    assert response.status_code == 422

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/skills/skill-test/permissions/usage?days=366")
    assert response.status_code == 422
