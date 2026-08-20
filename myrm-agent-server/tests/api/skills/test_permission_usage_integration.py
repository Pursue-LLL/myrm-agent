"""Real-DB integration tests for the skill permission usage endpoint.

Runs the production wiring end-to-end: usage rows are inserted through the real
``get_session`` into the per-test SQLite schema, the skill lookup goes through the
real ``skills_service.get_skill`` against a local skill seeded on disk, and the
endpoint executes the production aggregation query — no business-logic mocks.

The schema and session factory are provisioned per-test by the autouse
``setup_test_database`` fixture in ``tests/api/skills/conftest.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.skills.permissions import router as permissions_router
from app.core.skills.providers.local import compute_local_skill_id
from app.database.connection import get_session
from app.database.models import SkillPermissionUsageLog

_SKILL_NAME = "usage-skill"


@pytest.fixture
def usage_app() -> FastAPI:
    app = FastAPI()
    app.include_router(permissions_router, prefix="/api/v1/skills")
    return app


@pytest.fixture
def real_local_skill(tmp_path: Path) -> str:
    """Point the local skill provider at a temp dir containing a real SKILL.md."""
    import app.api.skills.sync as sync_module
    import app.core.skills.models as models_module
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.store.service import skills_service

    test_path = tmp_path / "skills"
    skill_dir = test_path / _SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {_SKILL_NAME}\ndescription: Usage stats integration skill\n---\n\n## Steps\n1. Do the thing.\n",
        encoding="utf-8",
    )
    skill_id = compute_local_skill_id(skill_dir)

    original_path = skill_creation_service.base_path
    original_default_paths = models_module.DEFAULT_LOCAL_SKILL_PATHS.copy()
    original_local_skills = skills_service._local_skills

    skill_creation_service.base_path = test_path
    sync_module.LOCAL_SKILLS_DIR = test_path
    models_module.DEFAULT_LOCAL_SKILL_PATHS.clear()
    models_module.DEFAULT_LOCAL_SKILL_PATHS.append(str(test_path))
    skills_service._local_skills = None

    yield skill_id

    skill_creation_service.base_path = original_path
    sync_module.LOCAL_SKILLS_DIR = original_path
    models_module.DEFAULT_LOCAL_SKILL_PATHS.clear()
    models_module.DEFAULT_LOCAL_SKILL_PATHS.extend(original_default_paths)
    skills_service._local_skills = original_local_skills


def _log(
    skill_id: str,
    permission: str,
    operation: str,
    allowed: bool,
    deny_reason: str | None = None,
    age: timedelta = timedelta(hours=1),
    used_at: datetime | None = None,
) -> SkillPermissionUsageLog:
    if used_at is None:
        used_at = datetime.now(UTC).replace(tzinfo=None) - age
    return SkillPermissionUsageLog(
        user_id="integration-user",
        skill_id=skill_id,
        permission=permission,
        operation=operation,
        allowed=allowed,
        deny_reason=deny_reason,
        used_at=used_at,
    )


async def _insert_logs(skill_id: str, logs: list[SkillPermissionUsageLog]) -> None:
    async with get_session() as db:
        for log in logs:
            db.add(log)
        await db.commit()


async def _fetch_usage(usage_app: FastAPI, skill_id: str, days: int = 7) -> tuple[int, dict | None]:
    transport = ASGITransport(app=usage_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/skills/{skill_id}/permissions/usage?days={days}")
    if response.status_code != 200:
        return response.status_code, None
    return 200, response.json()


async def test_usage_real_db_aggregates_permission_groups(usage_app: FastAPI, real_local_skill: str) -> None:
    skill_id = real_local_skill
    await _insert_logs(
        skill_id,
        [
            _log(skill_id, "file_read", "read a.txt", True, age=timedelta(hours=2)),
            _log(
                skill_id,
                "file_read",
                "read b.txt",
                False,
                "not granted",
                age=timedelta(minutes=30),
            ),
            _log(skill_id, "network_access", "GET https://example.com", True),
            _log(skill_id, "file_read", "read c.txt", True, age=timedelta(hours=1)),
        ],
    )

    status, payload = await _fetch_usage(usage_app, skill_id)

    assert status == 200
    assert payload is not None
    assert payload["skill_id"] == skill_id
    assert payload["skill_name"] == _SKILL_NAME
    assert payload["total_operations"] == 4

    stats = {s["permission"]: s for s in payload["stats"]}
    assert stats["file_read"]["total_count"] == 3
    assert stats["file_read"]["allowed_count"] == 2
    assert stats["file_read"]["denied_count"] == 1
    assert stats["network_access"]["total_count"] == 1
    assert stats["network_access"]["allowed_count"] == 1
    assert stats["network_access"]["denied_count"] == 0
    assert stats["file_read"]["recent_operations"][0]["deny_reason"] == "not granted"


async def test_usage_real_db_days_window_filters_old_logs(usage_app: FastAPI, real_local_skill: str) -> None:
    skill_id = real_local_skill
    await _insert_logs(
        skill_id,
        [
            _log(skill_id, "shell_exec", "recent cmd", True, age=timedelta(hours=1)),
            _log(skill_id, "shell_exec", "old cmd", True, age=timedelta(days=9)),
        ],
    )

    _, payload_7d = await _fetch_usage(usage_app, skill_id, days=7)
    assert payload_7d is not None
    assert payload_7d["total_operations"] == 1
    assert payload_7d["stats"][0]["recent_operations"][0]["operation"] == "recent cmd"

    _, payload_30d = await _fetch_usage(usage_app, skill_id, days=30)
    assert payload_30d is not None
    assert payload_30d["total_operations"] == 2


async def test_usage_real_db_recent_operations_capped_at_ten(usage_app: FastAPI, real_local_skill: str) -> None:
    skill_id = real_local_skill
    await _insert_logs(
        skill_id,
        [_log(skill_id, "env_var_access", f"op {i}", True, age=timedelta(hours=12 - i)) for i in range(12)],
    )

    _, payload = await _fetch_usage(usage_app, skill_id)

    assert payload is not None
    assert payload["total_operations"] == 12
    stats = payload["stats"]
    assert len(stats) == 1
    assert stats[0]["total_count"] == 12
    recent = stats[0]["recent_operations"]
    assert len(recent) == 10
    assert recent[0]["operation"] == "op 11"
    assert {op["operation"] for op in recent} == {f"op {i}" for i in range(2, 12)}


async def test_usage_real_db_unknown_skill_returns_404(usage_app: FastAPI) -> None:
    transport = ASGITransport(app=usage_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/skills/local::missing/permissions/usage")
    assert response.status_code == 404


async def test_usage_real_db_empty_logs_return_zero(usage_app: FastAPI, real_local_skill: str) -> None:
    status, payload = await _fetch_usage(usage_app, real_local_skill)

    assert status == 200
    assert payload is not None
    assert payload["total_operations"] == 0
    assert payload["stats"] == []


async def test_usage_real_db_same_timestamp_sorted_by_id_desc(usage_app: FastAPI, real_local_skill: str) -> None:
    """同 used_at 时按 id DESC 二级排序：后写入的（更大 id）在前。"""
    skill_id = real_local_skill
    same_ts = datetime.now(UTC).replace(tzinfo=None)
    await _insert_logs(
        skill_id,
        [
            _log(skill_id, "shell_exec", "first", True, used_at=same_ts),
            _log(skill_id, "shell_exec", "second", True, used_at=same_ts),
            _log(skill_id, "shell_exec", "third", True, used_at=same_ts),
        ],
    )

    _, payload = await _fetch_usage(usage_app, skill_id)

    assert payload is not None
    recent = payload["stats"][0]["recent_operations"]
    assert [op["operation"] for op in recent] == ["third", "second", "first"]


async def test_usage_real_db_recent_capped_per_permission(usage_app: FastAPI, real_local_skill: str) -> None:
    """每个权限独立保留最近 10 条，互不干扰。"""
    skill_id = real_local_skill
    logs: list[SkillPermissionUsageLog] = []
    for perm in ("file_read", "network_access"):
        for i in range(12):
            logs.append(
                _log(
                    skill_id,
                    perm,
                    f"{perm} op {i}",
                    True,
                    age=timedelta(hours=12 - i),
                )
            )
    await _insert_logs(skill_id, logs)

    _, payload = await _fetch_usage(usage_app, skill_id)

    assert payload is not None
    assert payload["total_operations"] == 24
    stats = {s["permission"]: s for s in payload["stats"]}
    for perm in ("file_read", "network_access"):
        assert stats[perm]["total_count"] == 12
        assert len(stats[perm]["recent_operations"]) == 10


async def test_usage_real_db_valid_days_boundaries(usage_app: FastAPI, real_local_skill: str) -> None:
    """days 有效边界 1 / 365 正常返回（Query ge=1, le=365）。"""
    skill_id = real_local_skill
    await _insert_logs(
        skill_id,
        [
            _log(skill_id, "file_read", "recent", True, age=timedelta(hours=1)),
            _log(skill_id, "file_read", "old", True, age=timedelta(days=364)),
        ],
    )

    _, payload_1d = await _fetch_usage(usage_app, skill_id, days=1)
    assert payload_1d is not None
    assert payload_1d["total_operations"] == 1

    _, payload_365d = await _fetch_usage(usage_app, skill_id, days=365)
    assert payload_365d is not None
    assert payload_365d["total_operations"] == 2


async def test_usage_real_db_logger_flush_to_read(usage_app: FastAPI, real_local_skill: str) -> None:
    """端到端真实链路：permission_logger 批量落库（无 mock）→ 端点聚合读取。"""
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from app.core.skills.gates import permission_logger as pl
    from app.platform_utils import get_session_factory

    skill_id = real_local_skill

    @asynccontextmanager
    async def _test_session():
        async with get_session_factory()() as session:
            try:
                yield session
            finally:
                await session.close()

    batch: list[pl._PermissionLogItem] = [
        {
            "user_id": "integration-user",
            "skill_id": skill_id,
            "permission": "code_execute",
            "operation": "run ok",
            "allowed": True,
            "deny_reason": "",
        },
        {
            "user_id": "integration-user",
            "skill_id": skill_id,
            "permission": "code_execute",
            "operation": "run blocked",
            "allowed": False,
            "deny_reason": "policy",
        },
    ]
    with patch("app.core.skills.gates.permission_logger.get_session", _test_session):
        await pl._async_flush_batch(batch)

    status, payload = await _fetch_usage(usage_app, skill_id)

    assert status == 200
    assert payload is not None
    assert payload["total_operations"] == 2
    stats = {s["permission"]: s for s in payload["stats"]}
    assert stats["code_execute"]["total_count"] == 2
    assert stats["code_execute"]["allowed_count"] == 1
    assert stats["code_execute"]["denied_count"] == 1
    recent = stats["code_execute"]["recent_operations"]
    assert recent[0]["operation"] == "run blocked"
    assert recent[0]["deny_reason"] == "policy"
