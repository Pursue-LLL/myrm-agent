"""HTTP contract: skill version list/compare/detail/rollback payloads."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.optimization.types import SkillVersion

from app.api.skill_optimization.dependencies import get_storage
from app.api.skill_optimization.routes import versions as versions_routes

ClientFactory = Callable[[list[SkillVersion]], TestClient]


def _version(number: int, *, active: bool = False) -> SkillVersion:
    return SkillVersion(
        skill_id="skill-1",
        version=number,
        content=f"content-v{number}",
        created_at=datetime(2026, 1, number),
        created_by="llm",
        is_active=active,
    )


class _FakeStorage:
    def __init__(self, versions: list[SkillVersion]) -> None:
        self._versions = {v.version: v for v in versions}

    async def get_skill_version(self, skill_id: str, version: int) -> SkillVersion | None:
        return self._versions.get(version)

    async def get_active_version(self, skill_id: str) -> SkillVersion | None:
        return next((v for v in self._versions.values() if v.is_active), None)


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    clients: list[TestClient] = []

    def _make(versions: list[SkillVersion]) -> TestClient:
        app = FastAPI()
        app.include_router(versions_routes.router, prefix="/api/v1/skill-optimization")
        app.dependency_overrides[get_storage] = lambda: _FakeStorage(versions)
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.close()


def test_compare_reports_content_change_without_score_fields(make_client: ClientFactory) -> None:
    client = make_client([_version(1), _version(2)])

    body = client.get("/api/v1/skill-optimization/versions/skill-1/compare", params={"v1": 1, "v2": 2}).json()

    assert body["content_changed"] is True
    assert body["v1"]["content"] == "content-v1"
    assert "score_delta" not in body
    assert "quality_score" not in body["v1"]


def test_compare_unknown_version_returns_404(make_client: ClientFactory) -> None:
    client = make_client([_version(1)])

    response = client.get("/api/v1/skill-optimization/versions/skill-1/compare", params={"v1": 1, "v2": 9})

    assert response.status_code == 404


def test_detail_returns_content_and_provenance(make_client: ClientFactory) -> None:
    client = make_client([_version(1), _version(2, active=True)])

    body = client.get("/api/v1/skill-optimization/versions/skill-1/2").json()

    assert body["content"] == "content-v2"
    assert body["is_active"] is True
    assert body["created_by"] == "llm"
    assert "quality_score" not in body


def test_rollback_returns_real_versions_without_synthetic_audit_log(make_client: ClientFactory) -> None:
    client = make_client([_version(1), _version(2, active=True)])

    with patch(
        "app.services.skill_optimization.skill_version_sync.activate_version_with_disk_sync",
        new=AsyncMock(),
    ) as activate:
        response = client.post("/api/v1/skill-optimization/rollback/skill-1", params={"target_version": 1})

    assert response.status_code == 200
    body = response.json()
    assert (body["from_version"], body["to_version"]) == (2, 1)
    assert "audit_log" not in body
    activate.assert_awaited_once()
    assert activate.await_args.args[1:] == ("skill-1", 1)


def test_rollback_unknown_target_returns_404(make_client: ClientFactory) -> None:
    client = make_client([_version(1, active=True)])

    response = client.post("/api/v1/skill-optimization/rollback/skill-1", params={"target_version": 9})

    assert response.status_code == 404
