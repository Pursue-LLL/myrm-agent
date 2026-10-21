"""Unit and API integration tests for Git Worktree management and session checkout anchoring.

[INPUT]
- httpx, ASGITransport
- app.api.git.worktree_router::router
- app.services.git.worktree_service

[OUTPUT]
- Pytest test cases covering /git/worktrees and /git/sessions/{session_id}/checkout-anchor

[POS]
tests/api/git/test_worktree_router.py: Git 多工作区与会话检出锚定自动化回归测试。
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.git.worktree_router import router as git_worktree_router
from app.services.git.worktree_service import (
    GitWorktreeInfo,
    GitWorktreeService,
)

test_app = FastAPI()
test_app.include_router(git_worktree_router, prefix="/api/v1")


@pytest.fixture(autouse=True)
def reset_service_state():
    service = GitWorktreeService.get_instance()
    service._active_worktree_override.clear()
    service._session_anchors.clear()
    yield
    service._active_worktree_override.clear()
    service._session_anchors.clear()


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_worktrees_success(async_client: httpx.AsyncClient) -> None:
    mock_worktrees = [
        GitWorktreeInfo(
            path="/tmp/project-repo",
            branch="main",
            head_commit="a1b2c3d4",
            is_current=True,
            is_bare=False,
            is_dirty=False,
        ),
        GitWorktreeInfo(
            path="/tmp/project-repo/.worktrees/feature-x",
            branch="feature-x",
            head_commit="e5f60718",
            is_current=False,
            is_bare=False,
            is_dirty=True,
        ),
    ]

    with patch.object(GitWorktreeService, "list_worktrees", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_worktrees
        resp = await async_client.get("/api/v1/git/worktrees")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["branch"] == "main"
        assert data[0]["is_current"] is True
        assert data[1]["branch"] == "feature-x"
        assert data[1]["is_dirty"] is True


@pytest.mark.asyncio
async def test_create_worktree_success(async_client: httpx.AsyncClient) -> None:
    created_info = GitWorktreeInfo(
        path="/tmp/repo/.worktrees/experiment-v2",
        branch="experiment-v2",
        head_commit="HEAD",
        is_current=True,
    )
    with patch.object(GitWorktreeService, "create_worktree", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = created_info
        resp = await async_client.post(
            "/api/v1/git/worktrees",
            json={"branch": "experiment-v2", "base_ref": "HEAD"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["branch"] == "experiment-v2"
        assert data["is_current"] is True


@pytest.mark.asyncio
async def test_switch_worktree_success(async_client: httpx.AsyncClient) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        switched_info = GitWorktreeInfo(
            path=tmp_dir,
            branch="feature-perf",
            is_current=True,
        )
        with patch.object(GitWorktreeService, "switch_worktree", new_callable=AsyncMock) as mock_sw:
            mock_sw.return_value = switched_info
            resp = await async_client.post(
                "/api/v1/git/worktrees/switch",
                json={"worktree_path": tmp_dir},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["path"] == tmp_dir
            assert data["is_current"] is True


@pytest.mark.asyncio
async def test_remove_worktree_success(async_client: httpx.AsyncClient) -> None:
    with patch.object(GitWorktreeService, "remove_worktree", new_callable=AsyncMock) as mock_rm:
        mock_rm.return_value = True
        resp = await async_client.delete(
            "/api/v1/git/worktrees",
            params={"worktree_path": "/tmp/project/.worktrees/old-feature", "force": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["removed"] is True
        assert data["path"] == "/tmp/project/.worktrees/old-feature"


@pytest.mark.asyncio
async def test_session_checkout_anchor_flow(async_client: httpx.AsyncClient) -> None:
    session_id = "test-session-anchor-999"

    resp_initial = await async_client.get(f"/api/v1/git/sessions/{session_id}/checkout-anchor")
    assert resp_initial.status_code == 200
    init_data = resp_initial.json()
    assert init_data["session_id"] == session_id
    assert init_data["is_anchored"] is True

    bind_payload = {
        "checkout_ref": "feature/payment-v2",
        "worktree_path": "/workspace/.worktrees/payment-v2",
        "touched_files": [
            {"file_path": "src/checkout/flow.ts", "change_type": "modified"},
            {"file_path": "src/checkout/gateway.ts", "change_type": "created"},
        ],
    }
    resp_bind = await async_client.post(
        f"/api/v1/git/sessions/{session_id}/checkout-anchor",
        json=bind_payload,
    )
    assert resp_bind.status_code == 200
    bind_data = resp_bind.json()
    assert bind_data["checkout_ref"] == "feature/payment-v2"
    assert len(bind_data["touched_files"]) == 2
    assert bind_data["touched_files"][0]["file_path"] == "src/checkout/flow.ts"

    # Now verify GET returns updated anchor metadata
    resp_get = await async_client.get(f"/api/v1/git/sessions/{session_id}/checkout-anchor")
    assert resp_get.status_code == 200
    get_data = resp_get.json()
    assert get_data["checkout_ref"] == "feature/payment-v2"
    assert len(get_data["touched_files"]) == 2
