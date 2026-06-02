"""Tests for app/config/browser.py — deploy_mode to LaunchMode mapping."""

from __future__ import annotations

from unittest.mock import patch

from myrm_agent_harness.toolkits.browser.pool.config import _DEFAULT_CDP_ENDPOINT, LaunchMode

from app.config.browser import get_browser_pool_config


class TestGetBrowserPoolConfig:
    def test_local_mode_returns_auto_launch_mode(self) -> None:
        with patch("app.config.browser.is_local_mode", return_value=True):
            config = get_browser_pool_config()
            assert config.launch_mode == LaunchMode.AUTO

    def test_local_mode_default_cdp_endpoint(self) -> None:
        with patch("app.config.browser.is_local_mode", return_value=True):
            config = get_browser_pool_config()
            assert config.cdp_endpoint == _DEFAULT_CDP_ENDPOINT

    def test_local_mode_custom_cdp_port(self) -> None:
        with (
            patch("app.config.browser.is_local_mode", return_value=True),
            patch.dict("os.environ", {"CDP_PORT": "9333"}),
        ):
            config = get_browser_pool_config()
            assert config.cdp_endpoint == "http://127.0.0.1:9333"

    def test_sandbox_mode_returns_launch_mode(self) -> None:
        with patch("app.config.browser.is_local_mode", return_value=False):
            config = get_browser_pool_config()
            assert config.launch_mode == LaunchMode.LAUNCH

    def test_sandbox_mode_no_cdp_endpoint(self) -> None:
        with patch("app.config.browser.is_local_mode", return_value=False):
            config = get_browser_pool_config()
            assert config.cdp_endpoint is None
