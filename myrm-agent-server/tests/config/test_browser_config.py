"""Tests for app/config/browser.py — deploy_mode to LaunchMode mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from myrm_agent_harness.toolkits.browser.pool.config import _DEFAULT_CDP_ENDPOINT, LaunchMode

from app.config.browser import (
    get_browser_egress_guard,
    get_browser_launch_options,
    get_browser_pool_config,
    get_configured_browser_pool,
)


class TestGetBrowserPoolConfig:
    def test_local_mode_returns_auto_launch_mode(self) -> None:
        with patch("app.config.browser.is_local_mode", return_value=True):
            config = get_browser_pool_config()
            assert config.launch_mode == LaunchMode.AUTO

    def test_local_mode_default_cdp_endpoint(self) -> None:
        with (
            patch("app.config.browser.is_local_mode", return_value=True),
            patch.dict("os.environ", {}, clear=False),
            patch("app.config.browser.os.getenv", side_effect=lambda k, *a: None),
            patch("app.config.browser._resolve_local_cdp_endpoint", return_value=_DEFAULT_CDP_ENDPOINT),
        ):
            config = get_browser_pool_config()
            assert config.cdp_endpoint == _DEFAULT_CDP_ENDPOINT

    def test_local_mode_custom_cdp_port(self) -> None:
        with (
            patch("app.config.browser.is_local_mode", return_value=True),
            patch.dict("os.environ", {"CDP_PORT": "9333"}),
        ):
            config = get_browser_pool_config()
            assert config.cdp_endpoint == "http://127.0.0.1:9333"

    def test_e2e_bound_run_uses_e2e_endpoint_over_cdp_port(self) -> None:
        """The E2E binding wins over CDP_PORT.

        Resolution must consult the E2E binding before ``CDP_PORT``: otherwise a stale
        user-Chrome port could win and the pool would attach to the wrong browser
        (no usable page → takeover tool fails while the test still passes).
        """
        with (
            patch("app.config.browser.is_local_mode", return_value=True),
            patch.dict(
                "os.environ",
                {"CDP_PORT": "9222", "MYRM_CHROME_E2E": "1", "MYRM_CHROME_E2E_PORT": "9333"},
            ),
        ):
            config = get_browser_pool_config()
            assert config.cdp_endpoint == "http://127.0.0.1:9333"

    def test_port_env_binds_e2e_without_the_switch(self) -> None:
        """``MYRM_CHROME_E2E_PORT`` alone is ownership intent.

        The E2E toolchain exports this port (via ``apply_browser_pool_env``) and never
        exports ``MYRM_CHROME_E2E``, so requiring the switch would leave the pool free to
        attach to a developer's own Chrome. Its presence is therefore sufficient to bind.
        """
        with (
            patch("app.config.browser.is_local_mode", return_value=True),
            patch.dict("os.environ", {"MYRM_CHROME_E2E_PORT": "9333"}, clear=True),
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


class TestGetBrowserLaunchOptions:
    def test_local_mode_visible_fallback_launch(self) -> None:
        with patch("app.config.browser.is_local_mode", return_value=True):
            options = get_browser_launch_options()
            assert options["headless"] is False

    def test_sandbox_mode_keeps_default_headless(self) -> None:
        with (
            patch("app.config.browser.is_local_mode", return_value=False),
            patch.dict("os.environ", {"VISUAL_DESKTOP": ""}, clear=False),
        ):
            options = get_browser_launch_options()
            assert options["headless"] is True


_CREATE_GUARD = "myrm_agent_harness.toolkits.browser.pool.create_egress_guard"
_CREATE_POOL = "myrm_agent_harness.toolkits.browser.pool.get_global_browser_pool"


class TestGetBrowserEgressGuard:
    """Which deployments put their browsers behind the connection guard; whether the policy applies is the harness's call."""

    def test_local_mode_has_none_because_its_sessions_may_reach_private_networks(self) -> None:
        with (
            patch("app.config.browser.is_local_mode", return_value=True),
            patch(_CREATE_GUARD) as create_guard,
        ):
            assert get_browser_egress_guard() is None

        create_guard.assert_not_called()

    def test_cloud_mode_takes_the_guard_the_harness_creates(self) -> None:
        guard = MagicMock(name="guard")

        with (
            patch("app.config.browser.is_local_mode", return_value=False),
            patch(_CREATE_GUARD, return_value=guard),
        ):
            assert get_browser_egress_guard() is guard

    def test_cloud_mode_where_the_policy_cannot_apply_has_none(self) -> None:
        with (
            patch("app.config.browser.is_local_mode", return_value=False),
            patch(_CREATE_GUARD, return_value=None),
        ):
            assert get_browser_egress_guard() is None

    def test_the_configured_pool_is_created_with_the_guard_of_the_deployment(self) -> None:
        guard = MagicMock(name="guard")

        with (
            patch("app.config.browser.get_browser_egress_guard", return_value=guard),
            patch(_CREATE_POOL) as create_pool,
        ):
            get_configured_browser_pool()

        assert create_pool.call_args.kwargs["egress_guard"] is guard
