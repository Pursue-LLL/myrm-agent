"""Integration tests for the foreground permission gate of desktop_vision_action.

Exercises the REAL integration path:
  desktop_vision_action → is_foreground_required → check_foreground_permission → callback

Only the hardware backend and platform-specific AX layer are mocked (no real screen).
The session, safety module, and permission logic are NOT mocked — this validates
the full chain works end-to-end within the harness.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    ExecutionMode,
    ForegroundPermissionResult,
    ForegroundPermissionScope,
)
from tests.toolkits.computer_use._foreground_permission_support import (
    NON_SENSITIVE_FG_INFO,
    assert_control_blocked,
    make_backend,
)


class TestDesktopVisionActionPermissionIntegration:
    """Integration: desktop_vision_action full-path permission checks."""

    @pytest.mark.asyncio
    async def test_foreground_mode_proceeds_to_action(self) -> None:
        """In foreground mode, permission gate is skipped entirely — action executes."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.foreground, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        assert "permission denied" not in str(result).lower()
        backend.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_strict_blocks_without_callback(self) -> None:
        """background_strict + no callback → permission denied string returned."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        lowered = assert_control_blocked(result)
        assert (
            "background_strict" in lowered
            or "no permission callback" in lowered
            or "desktop app control blocked" in lowered
        )
        backend.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_background_strict_callback_grants_proceeds(self) -> None:
        """background_strict + callback grants → action executes normally."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.session)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        callback.assert_called_once()
        assert "permission denied" not in str(result).lower()
        backend.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_strict_callback_denies_blocks(self) -> None:
        """background_strict + callback denies → action blocked."""
        backend = make_backend()
        callback = AsyncMock(return_value=ForegroundPermissionResult(granted=False))
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        callback.assert_called_once()
        assert_control_blocked(result)
        backend.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_scope_caches_foreground_after_app_approval(self) -> None:
        """Per-app approval runs each mutating vision call; foreground session grant persists."""
        backend = make_backend()
        callback = AsyncMock(
            return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.session)
        )
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            await session.desktop_vision_action(action="left_click", coordinate=[50, 50])
            session._last_snapshot_time = time.time()
            await session.desktop_vision_action(action="type", text="hello")

        # App approval callback each mutating vision action; foreground cached after first grant.
        assert callback.call_count == 2
        assert callback.call_args_list[0].kwargs["require_app_approval"] is True
        assert callback.call_args_list[1].kwargs["require_app_approval"] is True

    @pytest.mark.asyncio
    async def test_background_safe_actions_skip_permission(self) -> None:
        """'screenshot' and 'wait' are background-safe — no permission needed."""
        backend = make_backend()
        callback = AsyncMock()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=callback)

        with (
            patch(
                "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
                return_value=NON_SENSITIVE_FG_INFO,
            ),
            patch.object(session, "wait_seconds", new_callable=AsyncMock) as mock_wait,
        ):
            mock_wait.return_value = ActionResult(success=True)
            result = await session.desktop_vision_action(action="wait")

        callback.assert_not_called()
        assert "permission denied" not in result.lower() if isinstance(result, str) else True

    @pytest.mark.asyncio
    async def test_best_effort_mode_proceeds_without_callback(self) -> None:
        """background_best_effort + no callback → action proceeds (graceful degradation)."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_best_effort, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="left_click", coordinate=[50, 50])

        assert "permission denied" not in str(result).lower()
        backend.click.assert_called_once()


class TestVisionActionVariantsPermission:
    """Integration: non-click vision actions (type, key, scroll, drag) permission gate."""

    @pytest.mark.asyncio
    async def test_type_action_blocked_in_strict(self) -> None:
        """'type' action is foreground-requiring and gets blocked in strict mode."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="type", text="hello")

            assert_control_blocked(result)

    @pytest.mark.asyncio
    async def test_key_action_blocked_in_strict(self) -> None:
        """'key' action blocked without callback in strict mode."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="key", text="Return")

            assert_control_blocked(result)

    @pytest.mark.asyncio
    async def test_scroll_action_blocked_in_strict(self) -> None:
        """'scroll' action blocked in strict mode."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(
                action="scroll", coordinate=[100, 100], scroll_direction="down"
            )

            assert_control_blocked(result)

    @pytest.mark.asyncio
    async def test_drag_action_blocked_in_strict(self) -> None:
        """'drag' action blocked in strict mode."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(
                action="drag",
                start_coordinate=[10, 10],
                coordinate=[200, 200],
            )

            assert_control_blocked(result)

    @pytest.mark.asyncio
    async def test_mouse_move_blocked_in_strict(self) -> None:
        """'mouse_move' action blocked in strict mode."""
        backend = make_backend()
        config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict, screenshot_delay=0.0)
        session = DesktopSession(backend=backend, config=config, permission_callback=None)
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value=NON_SENSITIVE_FG_INFO,
        ):
            result = await session.desktop_vision_action(action="mouse_move", coordinate=[100, 100])

            assert_control_blocked(result)
