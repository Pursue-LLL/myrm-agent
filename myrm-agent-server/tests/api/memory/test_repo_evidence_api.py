"""Contract tests for Repo Evidence Digest API endpoint.

[INPUT]
- app.api.memory.operations.command_center::router

[OUTPUT]
- Integration test for repo evidence digest endpoint

[POS]
Tests repo git evidence inspection endpoint.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager


@pytest.fixture
def repo_client() -> TestClient:
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_crud_memory_manager] = lambda: MagicMock()
    return TestClient(app)


def test_get_repo_evidence_digest_endpoint(repo_client: TestClient) -> None:
    # Test on the current repository workspace
    cwd = str(Path.cwd())
    resp = repo_client.get(f"/api/memory/command-center/repo-evidence/digest?workspace_path={cwd}&max_commits=3")
    assert resp.status_code == 200
    data = resp.json()

    assert data["repo_name"] == "open-perplexity"
    assert "current_branch" in data
    assert "is_dirty" in data
    assert isinstance(data["recent_commits"], list)
    assert data["total_commits_examined"] > 0
    assert data["is_git_available"] is True

    if data["recent_commits"]:
        c = data["recent_commits"][0]
        assert "commit_hash" in c
        assert "short_hash" in c
        assert "author" in c
        assert "subject" in c
