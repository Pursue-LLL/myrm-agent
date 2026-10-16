"""POST /memory/reindex starts a background run (202); GET /memory/reindex/status reports it."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory._manager.reindex import (
    OrphanCollectionInfo,
    ReindexEstimate,
    ReindexResult,
)

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from app.services.memory import reindex_run
from app.services.memory.reindex_run import ReindexRun, ReindexRunState
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")
_SCHEDULE = "app.api.memory.operations.reindex.schedule_memory_reindex"


@pytest.fixture(autouse=True)
def _override_dependencies() -> Iterator[None]:
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    app.dependency_overrides[get_crud_memory_manager] = lambda: _manager()
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield
    app.dependency_overrides.pop(get_deploy_identity, None)
    app.dependency_overrides.pop(get_crud_memory_manager, None)


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    reindex_run._latest_run = None
    yield
    reindex_run._latest_run = None


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.estimate_reindex = AsyncMock(
        return_value=ReindexEstimate(
            total_memories=5,
            orphan_collections=[
                OrphanCollectionInfo(
                    collection_name="memory_semantic_old-model",
                    memory_type="semantic",
                    old_model_suffix="old-model",
                    document_count=5,
                )
            ],
        )
    )
    return manager


def test_status_is_idle_before_any_run(client: TestClient) -> None:
    response = client.get("/api/v1/memory/reindex/status")

    assert response.status_code == 200
    assert response.json() == {"state": "idle", "done": 0, "total": 0, "result": None}


def test_start_is_accepted_and_reports_the_run_in_flight(client: TestClient) -> None:
    run = ReindexRun(done=40, total=100)

    with patch(_SCHEDULE, new=MagicMock(return_value=run)) as schedule:
        response = client.post("/api/v1/memory/reindex")

    assert response.status_code == 202
    assert response.json() == {"state": "running", "done": 40, "total": 100, "result": None}
    schedule.assert_called_once()


def test_status_reports_the_outcome_of_a_finished_run_including_failures(client: TestClient) -> None:
    reindex_run._latest_run = ReindexRun(
        state=ReindexRunState.SUCCEEDED,
        done=100,
        total=100,
        result=ReindexResult(migrated=90, skipped=7, failed=3),
    )

    body = client.get("/api/v1/memory/reindex/status").json()

    assert body["state"] == "succeeded"
    assert body["result"] == {"migrated": 90, "skipped": 7, "failed": 3}


def test_status_reports_a_failed_run_without_an_outcome(client: TestClient) -> None:
    reindex_run._latest_run = ReindexRun(state=ReindexRunState.FAILED)

    body = client.get("/api/v1/memory/reindex/status").json()

    assert body["state"] == "failed"
    assert body["result"] is None


def test_estimate_lists_orphan_collections(client: TestClient) -> None:
    body = client.get("/api/v1/memory/reindex/estimate").json()

    assert body["total_memories"] == 5
    assert body["orphan_collections"][0]["old_model_suffix"] == "old-model"
