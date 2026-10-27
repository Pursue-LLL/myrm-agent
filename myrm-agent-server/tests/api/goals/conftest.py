"""Shared HTTP client for the goals router tests."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend


@pytest.fixture
def goal_stream_trigger() -> Iterator[AsyncMock]:
    """The unattended goal stream a resume starts: replaced so no test launches a real agent turn."""
    with patch(
        "app.services.agent.goals.goal_controls.trigger_goal_stream_with_failure_policy",
        new=AsyncMock(return_value=True),
    ) as trigger:
        yield trigger


@pytest.fixture
def client(tmp_path: Path, goal_stream_trigger: AsyncMock) -> Iterator[TestClient]:
    """A bare app that mounts only the goals router, backed by throwaway local storage."""
    from app.api.goals.router import router as goals_router

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")

    with (
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))),
        patch("app.api.goals.router.get_features") as mock_features,
    ):
        mock_features.return_value.get_bool.return_value = True
        with TestClient(app) as test_client:
            yield test_client
