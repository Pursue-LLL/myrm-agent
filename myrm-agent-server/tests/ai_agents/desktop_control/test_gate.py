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
