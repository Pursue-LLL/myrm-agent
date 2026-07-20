"""Integration: POST /webui/desktop/approval/resolve through real router + gate registry."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.ai_agents.desktop_control.gate import DesktopControlGate, resolve_desktop_control_approval
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_unknown_request_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/webui/desktop/approval/resolve",
        json={"request_id": "missing-request", "granted": True, "scope": "once"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_grants_pending_request_via_router(client: httpx.AsyncClient) -> None:
    gate = DesktopControlGate(workspace_root=None, auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _resolve_after_emit() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        response = await client.post(
            "/webui/desktop/approval/resolve",
            json={"request_id": request_id, "granted": True, "scope": "session"},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        task = asyncio.create_task(_resolve_after_emit())
        result = await gate(
            reason="Control Finder",
            operation="desktop_interact(click, @d1)",
            estimated_duration_seconds=1.0,
            app_name="Finder",
            timeout_seconds=2.0,
        )
        await task

    assert result.granted is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_deny_via_router(client: httpx.AsyncClient) -> None:
    gate = DesktopControlGate(workspace_root=None, auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _deny_after_emit() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        response = await client.post(
            "/webui/desktop/approval/resolve",
            json={"request_id": request_id, "granted": False, "scope": "once"},
        )
        assert response.status_code == 200

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        task = asyncio.create_task(_deny_after_emit())
        result = await gate(
            reason="Control Notes",
            operation="desktop_interact(type, @d2)",
            estimated_duration_seconds=1.0,
            app_name="Notes",
            timeout_seconds=2.0,
        )
        await task

    assert result.granted is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_always_persists_to_trust_list_across_workspace_roots(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    chat_workspace = tmp_path / "chat_workspace"
    server_cwd = tmp_path / "server_cwd"
    gate = DesktopControlGate(workspace_root=str(chat_workspace), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _resolve_always_after_emit() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        response = await client.post(
            "/webui/desktop/approval/resolve",
            json={"request_id": request_id, "granted": True, "scope": "always"},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        task = asyncio.create_task(_resolve_always_after_emit())
        result = await gate(
            reason="Control TextEdit",
            operation="desktop_interact(scroll, @d1)",
            estimated_duration_seconds=1.0,
            app_name="TextEdit",
            app_id="com.apple.TextEdit",
            timeout_seconds=2.0,
        )
        await task

    assert result.granted is True
    assert result.scope.value == "always"

    with patch("app.platform_utils.workspace_root.get_workspace_root", return_value=str(server_cwd)):
        list_response = await client.get("/webui/desktop/trust/apps")
        assert list_response.status_code == 200
        apps = list_response.json()["apps"]
        assert len(apps) == 1
        assert apps[0]["trust_key"] == "com.apple.TextEdit"

        revoke_response = await client.request(
            "DELETE",
            "/webui/desktop/trust/apps",
            json={"trust_key": "com.apple.TextEdit"},
        )
        assert revoke_response.status_code == 200

        empty_response = await client.get("/webui/desktop/trust/apps")
        assert empty_response.json()["apps"] == []


def test_direct_resolve_idempotent_after_pop() -> None:
    gate = DesktopControlGate(workspace_root=None, auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _run() -> tuple[str, bool]:
        with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
            pending_task = asyncio.create_task(
                gate(
                    reason="test",
                    operation="click",
                    estimated_duration_seconds=1.0,
                    app_name="Safari",
                    timeout_seconds=0.05,
                )
            )
            for _ in range(100):
                if sink.emit.await_args_list:
                    break
                await asyncio.sleep(0.01)
            request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
            first = resolve_desktop_control_approval(request_id, granted=True, scope="once")
            second = resolve_desktop_control_approval(request_id, granted=True, scope="once")
            await pending_task
            return request_id, first and not second

    request_id, only_once = asyncio.run(_run())
    assert request_id
    assert only_once is True
