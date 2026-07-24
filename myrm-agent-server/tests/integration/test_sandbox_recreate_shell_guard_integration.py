"""Integration: sandbox recreate guard blocks when shell jobs are running."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.meta_tools.bash.session_spawn_lifecycle import (
    reset_spawn_lifecycle_for_tests,
)
from myrm_agent_harness.api.hooks import (
    get_background_registry,
    set_global_background_job_finish_handler,
)

from app.services.agent.background_job_finish_handler import (
    ServerBackgroundJobFinishHandler,
)
from tests.integration.test_background_tasks_rest_api import _spawn_background


def _build_system_app():
    from fastapi import FastAPI

    from app.api.system.router import router as system_router

    app = FastAPI()
    app.include_router(system_router, prefix="/api/v1/system")
    return app


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    registry = get_background_registry()
    registry._entries.clear()  # type: ignore[attr-defined]
    reset_spawn_lifecycle_for_tests()
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())
    yield
    registry._entries.clear()  # type: ignore[attr-defined]
    reset_spawn_lifecycle_for_tests()
    set_global_background_job_finish_handler(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sandbox_recreate_returns_409_when_shell_jobs_running(
    tmp_path: Path,
) -> None:
    chat_id = f"recreate-guard-{uuid.uuid4().hex[:12]}"
    sleep_cmd = f'{sys.executable} -c "import time; time.sleep(60)"'
    await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=sleep_cmd,
        reason="recreate guard integration",
    )

    caps = MagicMock(is_sandbox_instance=True)
    settings = MagicMock()
    settings.control_plane.effective_url.return_value = "http://cp.test"
    settings.control_plane.sandbox_id = "sandbox-test"
    settings.control_plane.telemetry_token.get_secret_value.return_value = "token"

    transport = ASGITransport(app=_build_system_app())
    with (
        patch("app.api.system.router.get_deployment_capabilities", return_value=caps),
        patch("app.api.system.router.get_settings", return_value=settings),
    ):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post("/api/v1/system/sandbox/recreate")

    assert resp.status_code == 409
    assert "background shell job" in resp.json()["detail"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sandbox_recreate_allowed_when_no_shell_jobs(tmp_path: Path) -> None:
    caps = MagicMock(is_sandbox_instance=True)
    settings = MagicMock()
    settings.control_plane.effective_url.return_value = "http://cp.test"
    settings.control_plane.sandbox_id = "sandbox-test"
    settings.control_plane.telemetry_token.get_secret_value.return_value = "token"

    cp_response = MagicMock(status_code=200, text='{"status":"ok"}')

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=cp_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    transport = ASGITransport(app=_build_system_app())
    with (
        patch("app.api.system.router.get_deployment_capabilities", return_value=caps),
        patch("app.api.system.router.get_settings", return_value=settings),
        patch("app.api.system.router.httpx.AsyncClient", return_value=mock_client),
    ):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post("/api/v1/system/sandbox/recreate")

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
