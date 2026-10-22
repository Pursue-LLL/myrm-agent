"""Revoking a skill permission must take effect on the very next tool call: the checker's process-wide cache is cleared."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.backends.skills.types import SkillPermission

from app.api.dependencies import get_db_session
from app.api.skills.permissions import router as permissions_router
from app.services.skills import permission_service


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    permission_service.clear_permission_cache()
    yield
    permission_service.clear_permission_cache()


def _app_with_db(*, rows: list[tuple[str]] | None = None, rowcount: int = 1) -> FastAPI:
    async def _session() -> AsyncMock:
        result = Mock(rowcount=rowcount)
        result.fetchall.return_value = rows or []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)
        return session

    app = FastAPI()
    app.include_router(permissions_router, prefix="/api/v1/skills")
    app.dependency_overrides[get_db_session] = _session
    return app


async def test_revoke_drops_the_cached_grants_of_that_skill_only() -> None:
    permission_service._permission_cache["skill-a"] = {SkillPermission.SHELL_EXEC}
    permission_service._permission_cache["skill-b"] = {SkillPermission.SHELL_EXEC}

    async with AsyncClient(transport=ASGITransport(app=_app_with_db()), base_url="http://test") as client:
        response = await client.post("/api/v1/skills/skill-a/permissions/revoke", json={"permissions": ["shell_exec"]})

    assert response.status_code == 200
    assert "skill-a" not in permission_service._permission_cache
    assert "skill-b" in permission_service._permission_cache


async def test_bulk_revoke_by_type_drops_the_cached_grants_of_every_affected_skill() -> None:
    permission_service._permission_cache["skill-a"] = {SkillPermission.SHELL_EXEC}
    permission_service._permission_cache["skill-b"] = {SkillPermission.SHELL_EXEC}
    permission_service._permission_cache["skill-c"] = {SkillPermission.FILE_READ}
    app = _app_with_db(rows=[("skill-a",), ("skill-b",)], rowcount=2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/skills/permissions/bulk-revoke-by-type", json={"permission_type": "shell_exec"})

    assert response.status_code == 200
    assert response.json()["affected_skills"] == ["skill-a", "skill-b"]
    assert set(permission_service._permission_cache) == {"skill-c"}
