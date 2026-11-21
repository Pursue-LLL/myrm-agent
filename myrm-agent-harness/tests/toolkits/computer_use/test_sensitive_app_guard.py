"""Tests for sensitive application guardrail in safety.py and the desktop_session package.

Covers:
- is_sensitive_app: blocklist matching (financial, communication, password managers)
- The refusal reason names the matched application or keyword and never quotes the window title
- Integration with desktop_snapshot, desktop_interact, desktop_vision_action, desktop_vision_capture
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.safety import (
    _SENSITIVE_APPS,
    is_self_app,
    is_sensitive_app,
)


class TestIsSensitiveApp:
    """is_sensitive_app: detect sensitive foreground applications."""

    def test_empty_app_name_safe(self) -> None:
        assert is_sensitive_app("") is None

    def test_financial_alipay_cn(self) -> None:
        assert is_sensitive_app("支付宝") is not None
        assert "Blocked" in (is_sensitive_app("支付宝") or "")

    def test_financial_alipay_en(self) -> None:
        assert is_sensitive_app("Alipay") is not None

    def test_financial_bank(self) -> None:
        assert is_sensitive_app("招商银行") is not None
        assert is_sensitive_app("工商银行") is not None
        assert is_sensitive_app("Bank of America") is not None
        assert is_sensitive_app("Chase") is not None

    def test_financial_stock(self) -> None:
        assert is_sensitive_app("同花顺") is not None
        assert is_sensitive_app("东方财富") is not None

    def test_communication_wechat(self) -> None:
        assert is_sensitive_app("WeChat") is not None
        assert is_sensitive_app("微信") is not None

    def test_communication_telegram(self) -> None:
        assert is_sensitive_app("Telegram") is not None

    def test_communication_signal(self) -> None:
        assert is_sensitive_app("Signal") is not None

    def test_communication_enterprise(self) -> None:
        assert is_sensitive_app("企业微信") is not None
        assert is_sensitive_app("钉钉") is not None
        assert is_sensitive_app("飞书") is not None

    def test_password_manager_1password(self) -> None:
        assert is_sensitive_app("1Password 7") is not None

    def test_password_manager_bitwarden(self) -> None:
        assert is_sensitive_app("Bitwarden") is not None

    def test_password_manager_keychain(self) -> None:
        assert is_sensitive_app("Keychain Access") is not None

    def test_terminal_apps_blocked(self) -> None:
        assert is_sensitive_app("Terminal") is not None
        assert is_sensitive_app("iTerm2") is not None
        assert is_sensitive_app("Windows Terminal") is not None
        assert is_sensitive_app("powershell") is not None
        assert is_sensitive_app("GNOME Terminal") is not None
        assert is_sensitive_app("钥匙串访问") is not None

    def test_safe_apps(self) -> None:
        assert is_sensitive_app("Microsoft Excel") is None
        assert is_sensitive_app("Google Chrome") is None
        assert is_sensitive_app("Finder") is None
        assert is_sensitive_app("Visual Studio Code") is None
        assert is_sensitive_app("Safari") is None

    def test_case_insensitive(self) -> None:
        assert is_sensitive_app("WECHAT") is not None
        assert is_sensitive_app("telegram") is not None
        assert is_sensitive_app("1PASSWORD") is not None

    def test_substring_match(self) -> None:
        """Sensitive keyword matching works on substrings of app_name."""
        assert is_sensitive_app("com.tencent.xinwei.WeChat") is not None
        assert is_sensitive_app("中国工商银行 Personal") is not None

    def test_window_title_bank_in_chrome(self) -> None:
        """Browser showing bank site is blocked via window_title check."""
        result = is_sensitive_app("Google Chrome", window_title="招商银行 - 个人网银")
        assert result is not None
        assert "Window title" in result

    def test_window_title_safe(self) -> None:
        assert is_sensitive_app("Google Chrome", window_title="Google Search") is None

    def test_window_title_wechat_web(self) -> None:
        result = is_sensitive_app("Safari", window_title="微信读书 - WeChat")
        assert result is not None

    def test_window_title_empty_safe(self) -> None:
        assert is_sensitive_app("Finder", window_title="") is None

    def test_the_reason_for_a_window_title_never_quotes_it(self) -> None:
        """The reply and the log of a refusal must not carry the account, mailbox or contact in the title."""
        result = is_sensitive_app("Google Chrome", window_title="Chase - alice@example.com - Sign in")

        assert result is not None
        assert "Window title" in result
        assert "matched 'chase'" in result
        assert "alice@example.com" not in result

    def test_the_reason_for_the_agent_ui_never_quotes_the_window_title(self) -> None:
        result = is_self_app("Some App", window_title="desktop control panel - alice@example.com")

        assert result is not None
        assert "agent UI" in result
        assert "alice@example.com" not in result

    def test_returns_descriptive_message(self) -> None:
        result = is_sensitive_app("支付宝")
        assert result is not None
        assert "支付宝" in result
        assert "sensitive" in result.lower()

    def test_sensitive_apps_frozenset_non_empty(self) -> None:
        assert len(_SENSITIVE_APPS) > 0
        assert all(isinstance(s, str) for s in _SENSITIVE_APPS)


class TestDesktopSnapshotSensitiveGuard:
    """Integration: desktop_snapshot blocks sensitive apps."""

    @pytest.fixture
    def session(self):
        from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
        from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig

        backend = MagicMock()
        return DesktopSession(backend=backend, config=ComputerUseConfig())

    @pytest.mark.asyncio
    async def test_snapshot_blocked_for_sensitive_app(self, session) -> None:
        from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotMeta

        mock_meta = SnapshotMeta(
            ref_count=5,
            app_name="支付宝",
            window_title="余额",
            scope="foreground",
        )
        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.snapshot.capture_snapshot",
            return_value=(mock_meta, {}),
        ):
            result = await session.desktop_snapshot()
        assert isinstance(result, str)
        assert "Safety" in result
        assert "Blocked" in result

    @pytest.mark.asyncio
    async def test_snapshot_allowed_for_safe_app(self, session) -> None:
        from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotMeta

        mock_meta = SnapshotMeta(
            ref_count=3,
            app_name="Microsoft Excel",
            window_title="Sheet1",
            scope="foreground",
        )
        with (
            patch(
                "myrm_agent_harness.toolkits.computer_use.desktop_session.snapshot.capture_snapshot",
                return_value=(mock_meta, {}),
            ),
            patch(
                "myrm_agent_harness.toolkits.computer_use.desktop_session.snapshot.render_snapshot_tree",
                return_value=("tree text", mock_meta),
            ),
        ):
            result = await session.desktop_snapshot()
        assert isinstance(result, str)
        assert "Safety" not in result


class TestDesktopInteractSensitiveGuard:
    """Integration: desktop_interact blocks on re-validation when sensitive app detected."""

    @pytest.mark.asyncio
    async def test_interact_revalidation_blocks_sensitive_app(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
        from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
        from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig

        backend = MagicMock()
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        go = ElementRef(ref_id="c0", role="AXButton", name="Go", bbox=BBox(0, 0, 10, 10), backend_key="k")
        browsing = SnapshotMeta(ref_count=1, app_name="Safari", window_title="Start Page", scope="foreground", pid=7)
        (ref,) = session._refs.adopt({"c0": go}, browsing)
        session._last_snapshot_time = time.time() - 10.0

        # The same browser process now shows a sensitive page: the re-read must refuse it.
        sensitive_page = SnapshotMeta(ref_count=1, app_name="Safari", window_title="1Password", scope="target", pid=7)
        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.guards.capture_snapshot",
            return_value=(sensitive_page, {"c0": go}),
        ):
            result = await session.desktop_interact(ref=ref, action="click")

        assert isinstance(result, str)
        assert "Safety" in result
        assert "Blocked" in result
        assert session.ref_registry.meta == browsing


class TestDesktopVisionActionSensitiveGuard:
    """Integration: desktop_vision_action blocks when foreground is sensitive."""

    @pytest.mark.asyncio
    async def test_vision_action_blocks_sensitive_app(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
        from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig

        backend = MagicMock()
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        session._last_snapshot_time = time.time()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value={
                "app_name": "1Password 7",
                "window_title": "Vault",
                "interactive_estimate": 10,
                "needs_permission": False,
                "recommendation": "",
            },
        ):
            result = await session.desktop_vision_action(
                action="left_click",
                coordinate=[100, 200],
            )

        assert isinstance(result, str)
        assert "Safety" in result
        assert "Blocked" in result

    @pytest.mark.asyncio
    async def test_vision_action_allows_safe_app(self) -> None:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
        from myrm_agent_harness.toolkits.computer_use.types import (
            ActionResult,
            ComputerUseConfig,
            ScreenContext,
            ScreenInfo,
        )

        backend = MagicMock()
        backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
        backend.screen_context.return_value = ScreenContext(active_window="Chrome", mouse_x=100, mouse_y=200)
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        session._last_snapshot_time = time.time()
        session.click_at = AsyncMock(
            return_value=ActionResult(success=True, screenshot_base64="img", screenshot_size=(1920, 1080)),
        )

        with patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value={
                "app_name": "Google Chrome",
                "window_title": "Search",
                "interactive_estimate": 50,
                "needs_permission": False,
                "recommendation": "",
            },
        ):
            result = await session.desktop_vision_action(
                action="left_click",
                coordinate=[100, 200],
            )

        assert not isinstance(result, str) or "Safety" not in result


class TestDesktopVisionCaptureSensitiveGuard:
    """Integration: the screenshot entry refuses what the snapshot and the input entries refuse."""

    @pytest.fixture
    def session(self):
        from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
        from myrm_agent_harness.toolkits.computer_use.types import (
            ActionResult,
            ComputerUseConfig,
            ScreenContext,
            ScreenInfo,
        )

        backend = MagicMock()
        backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
        backend.screen_context.return_value = ScreenContext(active_window="Front", mouse_x=1, mouse_y=2)
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        session.take_screenshot = AsyncMock(
            return_value=ActionResult(success=True, screenshot_base64="img", screenshot_size=(1920, 1080)),
        )
        return session

    @staticmethod
    def _foreground(app_name: str, window_title: str = ""):
        return patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.vision.inspect_backend",
            return_value={"app_name": app_name, "window_title": window_title, "app_id": ""},
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("app_name", ["1Password 7", "WeChat", "Keychain Access"])
    async def test_capture_refused_for_sensitive_app(self, session, app_name: str) -> None:
        with self._foreground(app_name):
            result = await session.desktop_vision_capture()

        assert isinstance(result, str)
        assert result.startswith("Safety: Cannot view the screen.")
        assert "sensitive application" in result
        session.take_screenshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_capture_refused_for_sensitive_window_title(self, session) -> None:
        with self._foreground("Google Chrome", "招商银行 - 个人网银"):
            result = await session.desktop_vision_capture()

        assert isinstance(result, str)
        assert result.startswith("Safety: Cannot view the screen.")
        assert "Window title" in result
        assert "(matched '" in result
        assert "个人网银" not in result
        session.take_screenshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_capture_allowed_for_safe_app(self, session) -> None:
        with self._foreground("Microsoft Excel", "Sheet1"):
            result = await session.desktop_vision_capture()

        assert isinstance(result, list)
        assert result[0]["text"].startswith("Desktop vision capture.")
        session.take_screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_foreground_is_not_a_match(self, session) -> None:
        """Without a readable foreground identity the list cannot match, so the capture proceeds."""
        with self._foreground(""):
            result = await session.desktop_vision_capture()

        assert isinstance(result, list)
        session.take_screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_screenshot_action_still_refused_for_sensitive_app(self, session) -> None:
        with self._foreground("1Password 7"):
            result = await session.desktop_vision_action(action="screenshot")

        assert isinstance(result, str)
        assert "Blocked" in result
        session.take_screenshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_screenshot_action_probes_the_foreground_once(self, session) -> None:
        with self._foreground("Microsoft Excel") as probe:
            result = await session.desktop_vision_action(action="screenshot")

        assert isinstance(result, list)
        assert probe.call_count == 1
        session.take_screenshot.assert_awaited_once()
