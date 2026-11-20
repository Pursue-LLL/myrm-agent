import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.types import ScreenInfo


@pytest.fixture
def mock_backend():
    return MagicMock()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.screenshot_delay = 0.0
    return config


def _button(ref_id: str, name: str, backend_key: str = "key") -> ElementRef:
    return ElementRef(ref_id=ref_id, role="button", name=name, bbox=(0, 0, 10, 10), backend_key=backend_key)


def _test_app_meta() -> SnapshotMeta:
    return SnapshotMeta(ref_count=1, app_name="Test", window_title="Test", scope="foreground", needs_permission=False)


@pytest.mark.asyncio
async def test_desktop_interact_revalidation_success(mock_backend, mock_config):
    session = DesktopSession(backend=mock_backend, config=mock_config)
    (ref,) = session._refs.adopt({"c0": _button("c0", "Test", "old-key")}, _test_app_meta())
    session._last_snapshot_time = time.time() - 6.0  # Force timeout
    fresh_capture = {"c7": _button("c7", "Test", "fresh-key")}

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.guards.capture_snapshot",
            return_value=(_test_app_meta(), fresh_capture),
        ) as mock_capture,
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
    ):
        mock_invoke.return_value.success = True
        session.desktop_snapshot = AsyncMock(return_value="Follow up")

        result = await session.desktop_interact(ref=ref, action="click")

        mock_capture.assert_called_once_with(mock_backend, "target", "Test")
        assert mock_invoke.call_args.args[1].backend_key == "fresh-key"
        assert f"Action 'click' on @{ref} succeeded." in result


@pytest.mark.asyncio
async def test_desktop_interact_revalidation_failure_ref_missing(mock_backend, mock_config):
    session = DesktopSession(backend=mock_backend, config=mock_config)
    (ref,) = session._refs.adopt({"c0": _button("c0", "Test")}, _test_app_meta())
    session._last_snapshot_time = time.time() - 6.0  # Force timeout
    capture_without_the_element = {"c1": _button("c1", "Other")}

    with patch(
        "myrm_agent_harness.toolkits.computer_use.desktop_session.guards.capture_snapshot",
        return_value=(_test_app_meta(), capture_without_the_element),
    ):
        result = await session.desktop_interact(ref=ref, action="click")

        assert "Safety Re-validation failed" in result
        assert "is no longer found" in result


@pytest.mark.asyncio
async def test_desktop_vision_action_refreshes_stale_screenshot(mock_backend, mock_config):
    session = DesktopSession(backend=mock_backend, config=mock_config)
    session._last_snapshot_time = time.time() - 6.0

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value={"app_name": "Test", "window_title": "Test"},
        ),
        patch.object(session, "take_screenshot", new_callable=AsyncMock) as mock_shot,
    ):
        shot = MagicMock()
        shot.success = True
        mock_shot.return_value = shot
        with patch.object(session, "click_at", new_callable=AsyncMock) as mock_click:
            mock_click.return_value.success = True
            mock_click.return_value.screenshot_base64 = ""
            result = await session.desktop_vision_action(action="left_click", coordinate=[100, 100])

    mock_shot.assert_called_once()
    assert "completed" in result


@pytest.mark.asyncio
async def test_desktop_vision_action_requires_app_approval(mock_backend, mock_config):
    from myrm_agent_harness.toolkits.computer_use.types import (
        ComputerUseConfig,
        ExecutionMode,
        ForegroundPermissionResult,
        ForegroundPermissionScope,
    )

    callback = AsyncMock(return_value=ForegroundPermissionResult(granted=True, scope=ForegroundPermissionScope.once))
    config = ComputerUseConfig(execution_mode=ExecutionMode.background_strict)
    session = DesktopSession(backend=mock_backend, config=config, permission_callback=callback)
    session._last_snapshot_time = time.time()

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value={"app_name": "Safari", "window_title": "Example"},
        ),
        patch.object(session, "click_at", new_callable=AsyncMock) as mock_click,
    ):
        mock_click.return_value.success = True
        mock_click.return_value.screenshot_base64 = ""
        await session.desktop_vision_action(action="left_click", coordinate=[100, 100])

    assert callback.call_count == 1
    assert callback.call_args.kwargs["app_name"] == "Safari"
    assert callback.call_args.kwargs["require_app_approval"] is True


@pytest.mark.asyncio
async def test_desktop_vision_action_success(mock_backend, mock_config):
    session = DesktopSession(backend=mock_backend, config=mock_config)
    session._last_snapshot_time = time.time()  # Fresh snapshot

    with patch.object(session, "click_at", new_callable=AsyncMock) as mock_click:
        mock_click.return_value.success = True
        mock_click.return_value.screenshot_base64 = ""
        result = await session.desktop_vision_action(action="left_click", coordinate=[100, 100])

        assert "completed" in result
        mock_click.assert_called_once()


@pytest.mark.asyncio
async def test_desktop_interact_revalidation_capture_error(mock_backend, mock_config):
    session = DesktopSession(backend=mock_backend, config=mock_config)
    (ref,) = session._refs.adopt({"c0": _button("c0", "Test")}, _test_app_meta())
    session._last_snapshot_time = time.time() - 10.0
    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.guards.capture_snapshot",
            side_effect=RuntimeError("capture failed"),
        ),
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
    ):
        result = await session.desktop_interact(ref=ref, action="click")
    assert "Could not re-verify screen state" in result
    mock_invoke.assert_not_called()


@pytest.mark.asyncio
async def test_an_unknown_reference_is_refused_as_stale_without_reading_the_screen(mock_backend, mock_config):
    session = DesktopSession(backend=mock_backend, config=mock_config)
    session._refs.adopt({"c0": _button("c0", "Test")}, _test_app_meta())
    session._last_snapshot_time = time.time() - 60.0
    with patch(
        "myrm_agent_harness.toolkits.computer_use.desktop_session.guards.capture_snapshot",
    ) as mock_capture:
        result = await session.desktop_interact(ref="d99", action="click")
    mock_capture.assert_not_called()
    assert "d99" in result
    assert "[REMEDY_HINT:" in result


@pytest.mark.asyncio
async def test_export_inspector_snapshot_success(mock_backend, mock_config):
    from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta

    mock_backend.screen_info.return_value = ScreenInfo(width=1440, height=900, dpi_scale=2.0)
    session = DesktopSession(backend=mock_backend, config=mock_config)
    meta = SnapshotMeta(
        ref_count=1,
        app_name="TestApp",
        window_title="Window",
        scope="foreground",
        needs_permission=False,
    )
    refs = {
        "e0": ElementRef(
            ref_id="e0",
            role="button",
            name="OK",
            bbox=BBox(0, 0, 10, 10),
            backend_key="k",
        )
    }
    shot = MagicMock()
    shot.success = True
    shot.screenshot_base64 = "img"
    shot.screenshot_size = (100, 80)

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.views.capture_snapshot",
            return_value=(meta, refs),
        ),
        patch.object(session, "take_screenshot", new_callable=AsyncMock, return_value=shot),
        patch.object(session, "_emit_view_update", new_callable=AsyncMock),
    ):
        payload = await session.export_inspector_snapshot()

    assert payload["app_name"] == "TestApp"
    assert payload["screenshot_base64"] == "img"
    assert payload["refs"]
    assert payload["screen_width"] == 1440
    assert payload["screen_height"] == 900
    assert payload["dpi_scale"] == 2.0
