"""Contract tests for Repo Evidence Digest endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.api import (
    RepoCommitItem,
    RepoHistoryEvidenceDigest,
)

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager


@pytest.fixture
def repo_evidence_client() -> TestClient:
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    async def _mock_db() -> AsyncMock:
        return AsyncMock()

    def _mock_manager() -> MagicMock:
        return MagicMock()

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_crud_memory_manager] = _mock_manager
    return TestClient(app)


def test_get_repo_evidence_digest_endpoint(repo_evidence_client: TestClient) -> None:
    mock_digest = RepoHistoryEvidenceDigest(
        repo_name="myrm-repo",
        repo_path="/tmp/mock-repo",
        current_branch="feature/payment-v2",
        is_dirty=False,
        recent_commits=(
            RepoCommitItem(
                commit_hash="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
                short_hash="a1b2c3d4",
                author="Alice",
                committed_at="2026-09-05T08:00:00+00:00",
                subject="feat: add payment gateway fallback",
                files_changed=("src/payment.ts", "tests/payment.test.ts"),
            ),
        ),
        total_commits_examined=1,
    )

    with patch(
        "app.services.memory.evidence.repo_digest_service.extract_repo_history_digest",
        return_value=mock_digest,
    ):
        resp = repo_evidence_client.get(
            "/api/memory/command-center/repo-evidence/digest?workspace_path=/tmp/mock-repo&max_commits=3"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_name"] == "myrm-repo"
        assert data["current_branch"] == "feature/payment-v2"
        assert data["is_dirty"] is False
        assert len(data["recent_commits"]) == 1
        assert data["recent_commits"][0]["short_hash"] == "a1b2c3d4"
        assert data["recent_commits"][0]["author"] == "Alice"
        assert data["recent_commits"][0]["files_changed"] == [
            "src/payment.ts",
            "tests/payment.test.ts",
        ]
        assert data["is_git_available"] is True
