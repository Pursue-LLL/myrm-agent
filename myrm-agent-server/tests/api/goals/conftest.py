"""Shared HTTP client for the goals router tests."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
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
