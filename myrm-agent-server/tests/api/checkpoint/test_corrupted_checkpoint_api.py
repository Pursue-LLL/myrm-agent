"""Tests for corrupted subagent checkpoint handling in the checkpoint API.

Verifies that a corrupted (unparseable) checkpoint file:
- resumes with a 400 (not a generic 500)
- can still be deleted (not blocked by a 500)
"""
from __future__ import annotations

from importlib import import_module
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

checkpoint_router_module = import_module("app.api.checkpoint.router")

app = build_minimal_app("checkpoint")


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch) -> None:
    """Point the router's global storage at a temp dir for each test."""
    storage = checkpoint_router_module.SubagentCheckpointStorage(storage_path=tmp_path / "ckpts")
    monkeypatch.setattr(checkpoint_router_module, "_checkpoint_storage", storage)
    yield storage


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


def _write_corrupt_checkpoint(storage, task_id: str) -> None:
    (storage._storage_path / f"{task_id}.json").write_text("not valid json", encoding="utf-8")


@pytest.mark.asyncio
async def test_resume_corrupted_checkpoint_returns_400(
    async_client: httpx.AsyncClient,
    _isolate_storage,
) -> None:
    _write_corrupt_checkpoint(_isolate_storage, "corrupt-task")

    response = await async_client.post(
        "/api/v1/checkpoint/resume",
        json={"task_id": "corrupt-task"},
    )

    assert response.status_code == 400
    assert "corrupted" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_corrupted_checkpoint_succeeds(
    async_client: httpx.AsyncClient,
    _isolate_storage,
) -> None:
    _write_corrupt_checkpoint(_isolate_storage, "corrupt-task")

    response = await async_client.delete("/api/v1/checkpoint/corrupt-task")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "task_id": "corrupt-task"}
    assert not (_isolate_storage._storage_path / "corrupt-task.json").exists()


@pytest.mark.asyncio
async def test_delete_missing_checkpoint_returns_404(
    async_client: httpx.AsyncClient,
    _isolate_storage,
) -> None:
    response = await async_client.delete("/api/v1/checkpoint/not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resume_missing_checkpoint_returns_404(
    async_client: httpx.AsyncClient,
    _isolate_storage,
) -> None:
    response = await async_client.post(
        "/api/v1/checkpoint/resume",
        json={"task_id": "not-exist"},
    )

    assert response.status_code == 404
