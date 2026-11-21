"""Integration tests for the foreground permission gate on the bbox fallback path.

Exercises the REAL integration paths:
  try_bbox_click → check_foreground_permission → callback
  desktop_interact → AX failure → try_bbox_click → permission gate

Only the hardware backend and platform-specific AX layer are mocked (no real screen).
The session, safety module, and permission logic are NOT mocked.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.execution.healer import try_bbox_click
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.types import (
    ComputerUseConfig,
    ExecutionMode,
    ForegroundPermissionResult,
    ForegroundPermissionScope,
)
from tests.toolkits.computer_use._foreground_permission_support import (
    NON_SENSITIVE_FG_INFO,
    make_backend,
    make_element,
)


class TestHealerBBoxClickPermissionIntegration:
    """Integration: try_bbox_click full-path permission checks."""

    @pytest.mark.asyncio
    async def test_bbox_click_blocked_in_strict_mode(self) -> None:
        """Healer fallback blocked when background_strict and no callback."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        element = make_element()

        result = await try_bbox_click(session=session, element=element, action="click", text="", modifiers=None)

        assert result.success is False
        assert "background_strict" in result.error
        backend.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_bbox_click_proceeds_after_grant(self) -> None:
        """Healer fallback proceeds when callback grants permission."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.once)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        element = make_element(x=50, y=60)

        result = await try_bbox_click(session=session, element=element, action="click", text="", modifiers=None)

        assert result.success is True
        callback.assert_called_once()
        backend.click.assert_called_once_with(70, 70, clicks=1, modifiers=None)

    @pytest.mark.asyncio
    async def test_bbox_fill_action_proceeds_after_grant(self) -> None:
        """Healer 'fill' action: click + type_text after permission grant."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.session)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        element = make_element(x=0, y=0)

        result = await try_bbox_click(session=session, element=element, action="fill", text="hello", modifiers=None)

        assert result.success is True
        backend.click.assert_called_once()
        backend.type_text.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_bbox_click_denied_by_callback(self) -> None:
        """Healer fallback blocked when callback explicitly denies."""
        backend = make_backend()
        callback = AsyncMock(return_value=ForegroundPermissionResult(granted=False))
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        element = make_element()

        result = await try_bbox_click(session=session, element=element, action="click", text="", modifiers=None)

        assert result.success is False
        assert "denied" in result.error.lower()
        backend.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_bbox_click_foreground_mode_skips_gate(self) -> None:
        """In foreground mode, healer proceeds without any permission check."""
        backend = make_backend()
        callback = AsyncMock()
        config = ComputerUseConfig(execution_mode=ExecutionMode.foreground)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        element = make_element(x=10, y=20)

        result = await try_bbox_click(session=session, element=element, action="click", text="", modifiers=None)

        assert result.success is True
        callback.assert_not_called()
        backend.click.assert_called_once()


class TestDesktopInteractPermissionIntegration:
    """Integration: desktop_interact → AX fail → try_bbox_click → permission gate."""

    @pytest.mark.asyncio
    async def test_interact_ax_fail_falls_to_bbox_blocked(self) -> None:
        """When AX invoke fails, healer is invoked and permission gate blocks."""
        from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotMeta

        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        element = make_element(x=100, y=200)
        meta = SnapshotMeta(
            ref_count=1,
            app_name="Safari",
            window_title="Page",
            scope="foreground",
            needs_permission=False,
        )
        (ref,) = session._refs.adopt({"capture-0": element}, meta)

        failed_invoke = AxInvokeResult.failed(AxFailure.UNSUPPORTED, "AX invoke not available")
        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element",
            return_value=failed_invoke,
        ):
            result = await session.desktop_interact(ref=ref, action="click")

        assert isinstance(result, str)
        assert "background_strict" in result.lower() or "denied" in result.lower()
        backend.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_interact_ax_fail_callback_grants_bbox_executes(self) -> None:
        """When AX fails and callback grants, bbox click proceeds."""
        from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotMeta

        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.session)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        session._last_snapshot_time = time.time()

        element = make_element(x=100, y=200)
        meta = SnapshotMeta(
            ref_count=1,
            app_name="Safari",
            window_title="Page",
            scope="foreground",
            needs_permission=False,
        )
        (ref,) = session._refs.adopt({"capture-0": element}, meta)

        failed_invoke = AxInvokeResult.failed(AxFailure.UNSUPPORTED, "AX invoke not available")
        with (
            patch(
                "myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element",
                return_value=failed_invoke,
            ),
            patch(
                "myrm_agent_harness.toolkits.computer_use.desktop_session.snapshot.capture_snapshot",
                return_value=(meta, {"capture-0": element}),
            ),
            patch(
                "myrm_agent_harness.toolkits.computer_use.desktop_session.snapshot.render_snapshot_tree",
                return_value=("tree text", meta),
            ),
        ):
            result = await session.desktop_interact(ref=ref, action="click")

        callback.assert_called_once()
        backend.click.assert_called_once()
        assert isinstance(result, str)
        assert "succeeded" in result.lower() or "click" in result.lower()


class TestAlwaysScopePersistence:
    """Integration: 'always' scope grant persists across different action types."""

    @pytest.mark.asyncio
    async def test_always_grant_persists_across_vision_and_healer(self) -> None:
        """After 'always' grant via vision action, healer also skips callback."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.always)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        assert callback.call_count == 1

        element = make_element(x=30, y=40)
        result = await try_bbox_click(session=session, element=element, action="click", text="", modifiers=None)
        assert result.success is True
        assert callback.call_count == 1  # NOT called again

    @pytest.mark.asyncio
    async def test_once_scope_does_not_persist(self) -> None:
        """'once' scope requires callback on every subsequent call."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.once)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)

        element1 = make_element(x=10, y=10)
        element2 = make_element(x=20, y=20)

        await try_bbox_click(session=session, element=element1, action="click", text="", modifiers=None)
        await try_bbox_click(session=session, element=element2, action="click", text="", modifiers=None)

        assert callback.call_count == 2


class TestCallbackArgsIntegration:
    """Integration: verify callback receives correct reason/operation from real code paths."""

    @pytest.mark.asyncio
    async def test_vision_action_callback_args(self) -> None:
        """Callback from desktop_vision_action has correct reason and operation."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.once)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        call_kwargs = callback.call_args.kwargs
        assert "Safari" in call_kwargs["reason"]
        assert call_kwargs["operation"] == "desktop_vision_action(left_click)"
        assert call_kwargs["require_app_approval"] is True
        assert call_kwargs["estimated_duration_seconds"] == 5.0

    @pytest.mark.asyncio
    async def test_healer_callback_args(self) -> None:
        """Callback from try_bbox_click has correct reason and operation."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.once)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        element = make_element(x=100, y=200)

        await try_bbox_click(session=session, element=element, action="click", text="", modifiers=None)

        call_kwargs = callback.call_args.kwargs
        assert "AX invoke failed for @e0" in call_kwargs["reason"]
        assert call_kwargs["operation"] == "bbox_click(120, 210)"
        assert call_kwargs["estimated_duration_seconds"] == 3.0
