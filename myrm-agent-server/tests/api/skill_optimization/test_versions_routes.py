"""HTTP contract: skill version list/compare/detail/rollback payloads."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore, SkillVersion

from app.api.skill_optimization.dependencies import get_storage
from app.api.skill_optimization.routes import versions as versions_routes

ClientFactory = Callable[[list[SkillVersion]], TestClient]

_PLACEHOLDER = SkillQualityScore(0.5, 0.5, 0.5, 0.5, 0.5)
_MEASURED_LOW = SkillQualityScore(0.6, 0.5, 0.4, 0.5, 0.3)
_MEASURED_HIGH = SkillQualityScore(0.9, 0.7, 0.6, 0.8, 0.3)


def _version(number: int, score: SkillQualityScore | None, *, active: bool = False) -> SkillVersion:
    return SkillVersion(
        skill_id="skill-1",
        version=number,
        content=f"content-v{number}",
        quality_score=score,
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


def test_compare_hides_placeholder_scores_and_delta(make_client: ClientFactory) -> None:
    client = make_client([_version(1, _PLACEHOLDER), _version(2, None)])

    body = client.get("/api/v1/skill-optimization/versions/skill-1/compare", params={"v1": 1, "v2": 2}).json()

    assert body["v1"]["quality_score"] is None
    assert body["v2"]["quality_score"] is None
    assert body["score_delta"] is None
    assert body["content_changed"] is True


def test_compare_reports_delta_for_measured_scores(make_client: ClientFactory) -> None:
    client = make_client([_version(1, _MEASURED_LOW), _version(2, _MEASURED_HIGH)])

    body = client.get("/api/v1/skill-optimization/versions/skill-1/compare", params={"v1": 1, "v2": 2}).json()

    assert body["v1"]["quality_score"]["overall_score"] == pytest.approx(_MEASURED_LOW.overall_score)
    assert body["score_delta"]["success_rate"] == pytest.approx(0.3)
    assert body["score_delta"]["user_satisfaction"] == pytest.approx(0.3)
    assert set(body["score_delta"]) == {
        "overall_score",
        "success_rate",
        "token_efficiency",
        "execution_time",
        "user_satisfaction",
    }


def test_detail_uses_same_score_rules_as_list(make_client: ClientFactory) -> None:
    client = make_client([_version(1, _PLACEHOLDER), _version(2, _MEASURED_HIGH)])

    placeholder = client.get("/api/v1/skill-optimization/versions/skill-1/1").json()
    measured = client.get("/api/v1/skill-optimization/versions/skill-1/2").json()

    assert placeholder["quality_score"] is None
    assert measured["quality_score"]["call_frequency"] == pytest.approx(0.3)


def test_rollback_returns_real_versions_without_synthetic_audit_log(make_client: ClientFactory) -> None:
    client = make_client([_version(1, None), _version(2, None, active=True)])

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
    client = make_client([_version(1, None, active=True)])

    response = client.post("/api/v1/skill-optimization/rollback/skill-1", params={"target_version": 9})

    assert response.status_code == 404
