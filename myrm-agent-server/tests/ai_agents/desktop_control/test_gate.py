"""Tests for DesktopControlGate server wiring."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.desktop_control.gate import DesktopControlGate, resolve_desktop_control_approval
from myrm_agent_harness.toolkits.computer_use.types import ForegroundPermissionScope


@pytest.mark.asyncio
async def test_auto_grant_skips_prompt(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=True)
    result = await gate(
        reason="test",
        operation="click",
        estimated_duration_seconds=1.0,
        app_name="Safari",
    )
    assert result.granted is True
    assert result.scope == ForegroundPermissionScope.always


@pytest.mark.asyncio
async def test_preapproved_app_skips_prompt(tmp_path: Path) -> None:
    approval_dir = tmp_path / ".agent" / "desktop_control"
    approval_dir.mkdir(parents=True)
    (approval_dir / "approved_apps.json").write_text(
        json.dumps({"apps": {"Safari": {"scope": "always"}}}),
        encoding="utf-8",
    )
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    result = await gate(
        reason="test",
        operation="click",
        estimated_duration_seconds=1.0,
        app_name="Safari",
        require_app_approval=True,
    )
    assert result.granted is True


@pytest.mark.asyncio
async def test_emit_and_resolve_approval(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _resolve_after_emit() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        resolve_desktop_control_approval(request_id, granted=True, scope="session")

    with patch(
        "app.ai_agents.desktop_control.gate.get_tool_progress_sink",
        return_value=sink,
    ):
        resolver = asyncio.create_task(_resolve_after_emit())
        result = await gate(
            reason="Control Finder",
            operation="desktop_interact(click, @d1)",
            estimated_duration_seconds=1.0,
            app_name="Finder",
            timeout_seconds=2.0,
        )
        await resolver

    emitted = sink.emit.await_args_list[0].args[0]
    assert emitted["type"] == "desktop_control_approval_request"
    assert result.granted is True
    assert result.scope == ForegroundPermissionScope.session


@pytest.mark.asyncio
async def test_empty_app_name_not_auto_preapproved(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    result = await gate(
        reason="test",
        operation="desktop_vision_action(left_click)",
        estimated_duration_seconds=1.0,
        app_name="",
        require_app_approval=True,
    )
    assert result.granted is False


@pytest.mark.asyncio
async def test_no_sink_denies(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=None):
        result = await gate(
            reason="test",
            operation="click",
            estimated_duration_seconds=1.0,
            app_name="Finder",
        )
    assert result.granted is False


@pytest.mark.asyncio
async def test_approval_timeout_denies(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        result = await gate(
            reason="slow user",
            operation="click",
            estimated_duration_seconds=1.0,
            app_name="Finder",
            timeout_seconds=0.05,
        )

    assert result.granted is False


@pytest.mark.asyncio
async def test_always_scope_persists_app(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _resolve_always() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        resolve_desktop_control_approval(request_id, granted=True, scope="always")

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        task = asyncio.create_task(_resolve_always())
        result = await gate(
            reason="Control Notes",
            operation="desktop_interact(type, @d2)",
            estimated_duration_seconds=1.0,
            app_name="Notes",
            timeout_seconds=2.0,
        )
        await task

    assert result.granted is True
    assert result.scope == ForegroundPermissionScope.always
    approval_file = tmp_path / ".agent" / "desktop_control" / "approved_apps.json"
    assert approval_file.is_file()
    payload = json.loads(approval_file.read_text(encoding="utf-8"))
    assert payload["apps"]["Notes"]["scope"] == "always"

    # Second call should skip prompt via persisted always list.
    result2 = await gate(
        reason="Control Notes again",
        operation="desktop_interact(click, @d3)",
        estimated_duration_seconds=1.0,
        app_name="Notes",
        require_app_approval=True,
    )
    assert result2.granted is True
    assert sink.emit.await_count == 1


@pytest.mark.asyncio
async def test_session_scope_preapproves_within_gate_instance(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _resolve_session() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        resolve_desktop_control_approval(request_id, granted=True, scope="session")

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        task = asyncio.create_task(_resolve_session())
        first = await gate(
            reason="Control Safari",
            operation="desktop_interact(click, @d1)",
            estimated_duration_seconds=1.0,
            app_name="Safari",
            timeout_seconds=2.0,
        )
        await task

    assert first.granted is True
    second = await gate(
        reason="Control Safari again",
        operation="desktop_interact(type, @d2)",
        estimated_duration_seconds=1.0,
        app_name="Safari",
        require_app_approval=True,
    )
    assert second.granted is True
    assert sink.emit.await_count == 1


def test_resolve_unknown_request_returns_false() -> None:
    assert resolve_desktop_control_approval("missing-id", granted=True, scope="once") is False


def test_resolve_invalid_scope_falls_back_to_once(tmp_path: Path) -> None:
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _run() -> None:
        with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
            task = asyncio.create_task(gate(
                reason="test",
                operation="click",
                estimated_duration_seconds=1.0,
                app_name="Finder",
                timeout_seconds=2.0,
            ))
            for _ in range(100):
                if sink.emit.await_args_list:
                    break
                await asyncio.sleep(0.01)
            request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
            resolve_desktop_control_approval(request_id, granted=True, scope="not-a-real-scope")
            result = await task
            assert result.granted is True
            assert result.scope == ForegroundPermissionScope.once

    asyncio.run(_run())


def test_corrupt_persisted_file_is_ignored(tmp_path: Path) -> None:
    approval_dir = tmp_path / ".agent" / "desktop_control"
    approval_dir.mkdir(parents=True)
    (approval_dir / "approved_apps.json").write_text("{not json", encoding="utf-8")
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    assert "safari" not in gate._always_approved_apps


def test_persist_app_noops_without_workspace() -> None:
    gate = DesktopControlGate(workspace_root=None, auto_grant=False)
    gate._persist_app("Finder")
    assert gate._approval_path() is None


def test_reset_runtime_approval_state_clears_session_and_reloads_disk(tmp_path: Path) -> None:
    approval_dir = tmp_path / ".agent" / "desktop_control"
    approval_dir.mkdir(parents=True)
    (approval_dir / "approved_apps.json").write_text(
        json.dumps({"apps": {"TextEdit": {"scope": "always"}}}),
        encoding="utf-8",
    )
    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    gate._session_approved_apps.add("notes")
    assert gate._is_app_preapproved("TextEdit")
    assert gate._is_app_preapproved("Notes")

    (approval_dir / "approved_apps.json").unlink()
    gate.reset_runtime_approval_state()
    assert not gate._is_app_preapproved("TextEdit")
    assert not gate._is_app_preapproved("Notes")


@pytest.mark.asyncio
async def test_always_scope_persists_after_corrupt_existing_file(tmp_path: Path) -> None:
    approval_dir = tmp_path / ".agent" / "desktop_control"
    approval_dir.mkdir(parents=True)
    (approval_dir / "approved_apps.json").write_text("{bad json", encoding="utf-8")

    gate = DesktopControlGate(workspace_root=str(tmp_path), auto_grant=False)
    sink = MagicMock()
    sink.emit = AsyncMock()

    async def _resolve_always() -> None:
        for _ in range(100):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.01)
        request_id = sink.emit.await_args_list[0].args[0]["data"]["request_id"]
        resolve_desktop_control_approval(request_id, granted=True, scope="always")

    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=sink):
        task = asyncio.create_task(_resolve_always())
        result = await gate(
            reason="Control Pages",
            operation="desktop_interact(click, @d1)",
            estimated_duration_seconds=1.0,
            app_name="Pages",
            timeout_seconds=2.0,
        )
        await task

    assert result.granted is True
    approval_file = tmp_path / ".agent" / "desktop_control" / "approved_apps.json"
    payload = json.loads(approval_file.read_text(encoding="utf-8"))
    assert payload["apps"]["Pages"]["scope"] == "always"
