"""MacOSBackend 分支与错误路径单测 — 补足既有方法的分支覆盖。

[INPUT]
- backends.macos::MacOSBackend（POS: macOS 平台 backend 实现）

[OUTPUT]
- 窗口目标解析、输入原语错误路径、凭证输入（vault 集成）、剪贴板粘贴编排、
  DPI 检测回退链、截屏可捕获探针、平台探测委托

[POS]
与 test_macos_backend.py（方法主路径）互补：本文件专职分支与错误路径。
纯 subprocess/to_thread mock，headless 安全、恒定 CPU 消耗。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.backends import macos as macos_mod
from myrm_agent_harness.toolkits.computer_use.backends import macos_permissions as permissions_mod
from myrm_agent_harness.toolkits.computer_use.backends.macos import (
    MacOSBackend,
    _detect_dpi_scale_quartz,
)
from myrm_agent_harness.toolkits.computer_use.backends.macos_background import _WindowTarget
from myrm_agent_harness.toolkits.computer_use.types import ScreenLockState

_VAULT_PATH = "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault"


@pytest.fixture()
def backend() -> MacOSBackend:
    return MacOSBackend()


class TestWindowTargetResolution:
    def test_returns_bounds_when_window_exists(self, backend: MacOSBackend) -> None:
        target = _WindowTarget(pid=9, window_id=3, bounds=(1, 2, 3, 4))
        with patch.object(macos_mod, "_resolve_target_window", MagicMock(return_value=target)):
            import asyncio

            assert asyncio.run(backend.resolve_window_target("Safari")) == (1, 2, 3, 4)

    def test_missing_window_returns_none(self, backend: MacOSBackend) -> None:
        import asyncio

        with patch.object(macos_mod, "_resolve_target_window", MagicMock(return_value=None)):
            assert asyncio.run(backend.resolve_window_target("Ghost")) is None


class TestInputPrimitiveErrorPaths:
    @pytest.mark.asyncio()
    async def test_click_error_is_reported(self, backend: MacOSBackend) -> None:
        with (
            patch.object(macos_mod.macos_input, "key_down"),
            patch.object(macos_mod.macos_input, "key_up"),
            patch.object(macos_mod.macos_input, "click", MagicMock(side_effect=RuntimeError("no accessibility"))),
        ):
            result = await backend.click(1, 2, modifiers=["ctrl"])
        assert result.success is False
        assert "no accessibility" in (result.error or "")

    @pytest.mark.asyncio()
    async def test_type_text_error_is_reported(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread", side_effect=RuntimeError("blocked")):
            result = await backend.type_text("hello")
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_key_single_press_branch(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread") as to_thread:
            result = await backend.key("escape")
        assert result.success is True
        assert to_thread.call_args[0][1] == "escape"

    @pytest.mark.asyncio()
    async def test_key_error_is_reported(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread", side_effect=RuntimeError("boom")):
            result = await backend.key("ctrl+c")
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_mouse_move_error_is_reported(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread", side_effect=RuntimeError("boom")):
            result = await backend.mouse_move(1, 2)
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_scroll_horizontal_branch(self, backend: MacOSBackend) -> None:
        calls: list[str] = []

        def _record(fn: object, *args: object, **kwargs: object) -> None:
            calls.append(getattr(fn, "__name__", str(fn)))

        with patch("asyncio.to_thread", side_effect=_record):
            result = await backend.scroll(1, 2, "left")
        assert result.success is True
        assert "hscroll" in calls
        assert "scroll" not in calls

    @pytest.mark.asyncio()
    async def test_scroll_error_is_reported(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread", side_effect=RuntimeError("boom")):
            result = await backend.scroll(1, 2, "down")
        assert result.success is False


class TestCredentialTyping:
    @pytest.mark.asyncio()
    async def test_password_path(self, backend: MacOSBackend) -> None:
        vault = MagicMock()
        vault.get_password.return_value = "hunter2"
        with (
            patch(_VAULT_PATH, return_value=vault),
            patch("asyncio.to_thread") as to_thread,
        ):
            result = await backend.type_credential("login")
        assert result.success is True
        vault.get_password.assert_called_once_with("login")
        assert to_thread.call_args[0][1] == "hunter2"

    @pytest.mark.asyncio()
    async def test_totp_path(self, backend: MacOSBackend) -> None:
        vault = MagicMock()
        vault.get_totp_token.return_value = "123456"
        with (
            patch(_VAULT_PATH, return_value=vault),
            patch("asyncio.to_thread"),
        ):
            result = await backend.type_credential("login-totp")
        assert result.success is True
        vault.get_totp_token.assert_called_once_with("login-totp")

    @pytest.mark.asyncio()
    async def test_vault_lookup_failure_returns_error(self, backend: MacOSBackend) -> None:
        vault = MagicMock()
        vault.get_password.side_effect = KeyError("absent")
        with patch(_VAULT_PATH, return_value=vault):
            result = await backend.type_credential("login")
        assert result.success is False
        assert "login" in (result.error or "")

    @pytest.mark.asyncio()
    async def test_typing_failure_returns_error(self, backend: MacOSBackend) -> None:
        vault = MagicMock()
        vault.get_password.return_value = "hunter2"
        with (
            patch(_VAULT_PATH, return_value=vault),
            patch("asyncio.to_thread", side_effect=RuntimeError("boom")),
        ):
            result = await backend.type_credential("login")
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_non_ascii_secret_uses_paste(self, backend: MacOSBackend) -> None:
        vault = MagicMock()
        vault.get_password.return_value = "密钥"
        with (
            patch(_VAULT_PATH, return_value=vault),
            patch.object(backend, "_paste_text", AsyncMock()) as paste,
        ):
            result = await backend.type_credential("login")
        assert result.success is True
        paste.assert_awaited_once_with("密钥", concealed=True)


class TestPasteTextDelegation:
    """_paste_text 把整个借用过程交给 macos_pasteboard.paste_text，在一个工作线程里跑完。"""

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("concealed", [False, True])
    async def test_delegates_once_with_settle_time_and_cmd_v(self, backend: MacOSBackend, concealed: bool) -> None:
        with (
            patch.object(macos_mod.macos_pasteboard, "paste_text") as paste_text,
            patch.object(macos_mod.macos_input, "hotkey") as hotkey,
        ):
            await backend._paste_text("你好", concealed=concealed)

            paste_text.assert_called_once()
            args, kwargs = paste_text.call_args
            assert args[0] == "你好"
            assert kwargs == {"concealed": concealed, "settle_seconds": macos_mod._PASTE_SETTLE_SECONDS}
            args[1]()  # 必须在补丁生效期间调用，否则会向本机真实投递 Cmd+V
            hotkey.assert_called_once_with("command", "v")

    @pytest.mark.asyncio()
    async def test_type_text_reports_paste_failure(self, backend: MacOSBackend) -> None:
        with patch.object(
            macos_mod.macos_pasteboard,
            "paste_text",
            side_effect=RuntimeError("Failed to write text to the macOS pasteboard"),
        ):
            result = await backend.type_text("你好")
        assert result.success is False
        assert "Failed to write text" in (result.error or "")


class TestPlatformDelegation:
    @pytest.mark.asyncio()
    async def test_window_text_delegates(self, backend: MacOSBackend) -> None:
        expected = MagicMock()
        with patch("asyncio.to_thread", AsyncMock(return_value=expected)):
            assert await backend.window_text() is expected

    @pytest.mark.asyncio()
    async def test_has_blocking_dialog_delegates(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread", AsyncMock(return_value=True)):
            assert await backend.has_blocking_dialog(["Safari"]) is True

    @pytest.mark.asyncio()
    async def test_is_browser_active_delegates(self, backend: MacOSBackend) -> None:
        with patch("asyncio.to_thread", AsyncMock(return_value=False)):
            assert await backend.is_browser_active() is False

    def test_is_screen_locked_delegates(self, backend: MacOSBackend) -> None:
        detector = MagicMock()
        detector.is_locked.return_value = True
        with patch(
            "myrm_agent_harness.toolkits.computer_use.screen_detector.get_default_screen_detector",
            return_value=detector,
        ):
            assert backend.is_screen_locked() is True

    def test_is_display_asleep_maps_lock_state(self, backend: MacOSBackend) -> None:
        detector = MagicMock()
        detector.get_state.return_value = ScreenLockState.SLEEPING
        with patch(
            "myrm_agent_harness.toolkits.computer_use.screen_detector.get_default_screen_detector",
            return_value=detector,
        ):
            assert backend.is_display_asleep() is True

        detector.get_state.return_value = ScreenLockState.LOCKED
        with patch(
            "myrm_agent_harness.toolkits.computer_use.screen_detector.get_default_screen_detector",
            return_value=detector,
        ):
            assert backend.is_display_asleep() is False

    @pytest.mark.asyncio()
    async def test_check_permissions_delegates_probe_flag(self, backend: MacOSBackend) -> None:
        expected = MagicMock()
        to_thread = AsyncMock(return_value=expected)
        with patch("asyncio.to_thread", to_thread):
            assert await backend.check_permissions(probe_capture=True) is expected
        assert to_thread.call_args[0][1] is True


class TestScreenInfoCaching:
    def test_second_call_returns_cached_value(self, backend: MacOSBackend) -> None:
        size = MagicMock(width=100, height=200)
        with (
            patch.object(macos_mod.macos_input, "size", MagicMock(return_value=size)),
            patch.object(macos_mod, "_detect_dpi_scale_quartz", MagicMock(return_value=2.0)) as dpi,
        ):
            first = backend.screen_info()
            second = backend.screen_info()
        assert first is second
        dpi.assert_called_once()


class TestDpiScaleDetection:
    def test_probe_success_wins(self) -> None:
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="2.0\n")
            assert _detect_dpi_scale_quartz(1920) == 2.0

    def test_probe_non_positive_falls_back_to_retina_scan(self) -> None:
        def _run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if cmd[0] == "python3":
                return MagicMock(returncode=0, stdout="0\n")
            return MagicMock(returncode=0, stdout="Resolution: 2880x1800 Retina")

        with patch("subprocess.run", side_effect=_run):
            assert _detect_dpi_scale_quartz(1440) == 2.0

    def test_all_probes_fail_defaults_to_one(self) -> None:
        with patch("subprocess.run", side_effect=OSError("no tools")):
            assert _detect_dpi_scale_quartz(1440) == 1.0


class TestBlockingDialogParsing:
    def test_malformed_output_is_false(self) -> None:
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="single-field-only")
            assert macos_mod._has_blocking_dialog(["Safari"]) is False

    def test_nonzero_exit_is_false(self) -> None:
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=1, stdout="Safari|||true")
            assert macos_mod._has_blocking_dialog(["Safari"]) is False


class TestCaptureProbe:
    def test_nonzero_exit_is_false(self) -> None:
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=1)
            assert permissions_mod._probe_screencapture_capturable() is False

    def test_missing_file_is_false(self) -> None:
        with (
            patch("subprocess.run", MagicMock(return_value=MagicMock(returncode=0))),
            patch("pathlib.Path.is_file", MagicMock(return_value=False)),
            patch("pathlib.Path.unlink"),
        ):
            assert permissions_mod._probe_screencapture_capturable() is False

    def test_success_defers_to_luminance_gate(self) -> None:
        with (
            patch("subprocess.run", MagicMock(return_value=MagicMock(returncode=0))),
            patch("pathlib.Path.is_file", MagicMock(return_value=True)),
            patch("pathlib.Path.read_bytes", MagicMock(return_value=b"PNG")),
            patch("pathlib.Path.unlink"),
            patch(
                "myrm_agent_harness.toolkits.computer_use.capture_probe.png_bytes_look_capturable",
                MagicMock(return_value=True),
            ) as gate,
        ):
            assert permissions_mod._probe_screencapture_capturable() is True
        gate.assert_called_once_with(b"PNG")

    def test_os_error_is_false(self) -> None:
        with patch("subprocess.run", side_effect=OSError("no screencapture")):
            assert permissions_mod._probe_screencapture_capturable() is False
