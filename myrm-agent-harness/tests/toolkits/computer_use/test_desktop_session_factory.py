"""create_desktop_session holds the platform's own backend, also where a cua-driver proxy would be installed.

The accessibility capture, the foreground identity and the sensitive-application guards route on the
backend's own class. A desktop session built on the cua-driver proxy therefore reads as an unsupported
platform: its snapshot fails and its guards see no application at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use import create_desktop_session
from myrm_agent_harness.toolkits.computer_use.backends.cua_driver.backend import CuaDriverBackend
from myrm_agent_harness.toolkits.computer_use.backends.linux.backend import LinuxBackend
from myrm_agent_harness.toolkits.computer_use.perception import linux_ax
from myrm_agent_harness.toolkits.computer_use.session import create_computer_session
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig


@pytest.fixture
def cua_driver_installed() -> Iterator[None]:
    """A Linux host with the cua-driver binary on PATH."""
    linux = MagicMock()
    linux.os_type = "linux"
    with (
        patch("myrm_agent_harness.toolkits.code_execution.platform.detect_platform", return_value=linux),
        patch(
            "myrm_agent_harness.toolkits.computer_use.backends.cua_driver.backend.is_cua_driver_available",
            return_value=True,
        ),
    ):
        yield


@pytest.mark.usefixtures("cua_driver_installed")
def test_a_desktop_session_holds_the_native_backend() -> None:
    assert isinstance(create_computer_session()._backend, CuaDriverBackend)

    assert type(create_desktop_session()._backend) is LinuxBackend


@pytest.mark.usefixtures("cua_driver_installed")
def test_config_and_callbacks_reach_the_session() -> None:
    config = ComputerUseConfig()
    permission_callback = AsyncMock()
    view_update_callback = MagicMock()

    session = create_desktop_session(
        config=config, view_update_callback=view_update_callback, permission_callback=permission_callback
    )

    assert session._config is config
    assert session._permission_callback is permission_callback
    assert session._view_update_callback is view_update_callback


@pytest.mark.asyncio
@pytest.mark.usefixtures("cua_driver_installed")
async def test_the_sensitive_application_guard_sees_the_front_application() -> None:
    """With cua-driver installed, a screenshot is still refused while a password manager is in front."""
    session = create_desktop_session()
    front = {"app_name": "1Password", "window_title": "", "app_id": ""}

    with (
        patch.object(LinuxBackend, "is_screen_locked", return_value=False),
        patch.object(LinuxBackend, "is_display_asleep", return_value=False),
        patch.object(linux_ax, "inspect_foreground", return_value=front),
    ):
        result = await session.desktop_vision_capture()

    assert isinstance(result, str)
    assert result.startswith("Safety: Cannot view the screen.")
    assert "1Password" in result
