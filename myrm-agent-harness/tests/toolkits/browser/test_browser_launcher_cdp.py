"""Unit tests for BrowserLauncher: CDP probe and connect, launch-mode routing, E2E Chrome binding."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.exceptions import BrowserLaunchError
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import (
    BrowserInstance,
    BrowserLauncher,
)
from myrm_agent_harness.toolkits.browser.pool.config import (
    _DEFAULT_CDP_ENDPOINT,
    LaunchMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_browser(contexts: int = 0) -> MagicMock:
    browser = MagicMock()
    browser.contexts = [MagicMock() for _ in range(contexts)]
    return browser


def _make_launcher(
    launch_mode: LaunchMode = LaunchMode.LAUNCH,
    cdp_endpoint: str | None = None,
) -> BrowserLauncher:
    return BrowserLauncher(
        launch_options={"headless": True},
        launch_mode=launch_mode,
        cdp_endpoint=cdp_endpoint,
    )


# ---------------------------------------------------------------------------
# BrowserInstance.is_managed
# ---------------------------------------------------------------------------


class TestBrowserInstanceIsManaged:
    def test_default_is_managed_true(self) -> None:
        inst = BrowserInstance(browser=_mock_browser())
        assert inst.is_managed is True

    def test_explicit_is_managed_false(self) -> None:
        inst = BrowserInstance(browser=_mock_browser(), is_managed=False)
        assert inst.is_managed is False


# ---------------------------------------------------------------------------
# BrowserLauncher init
# ---------------------------------------------------------------------------


class TestBrowserLauncherInit:
    def test_default_launch_mode(self) -> None:
        launcher = _make_launcher()
        assert launcher._launch_mode == LaunchMode.LAUNCH

    def test_custom_launch_mode(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.CONNECT, cdp_endpoint="http://host:1234")
        assert launcher._launch_mode == LaunchMode.CONNECT
        assert launcher._cdp_endpoint == "http://host:1234"

    def test_cdp_endpoint_defaults_when_none(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO, cdp_endpoint=None)
        assert launcher._cdp_endpoint == _DEFAULT_CDP_ENDPOINT


# ---------------------------------------------------------------------------
# _probe_cdp
# ---------------------------------------------------------------------------


class TestProbeCdp:
    @pytest.mark.asyncio
    async def test_probe_success(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        with patch(
            "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.probe_cdp_endpoint",
            return_value=True,
        ):
            result = await launcher._probe_cdp("http://127.0.0.1:9222")
            assert result is True

    @pytest.mark.asyncio
    async def test_probe_failure_connection_refused(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        with patch(
            "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.probe_cdp_endpoint",
            return_value=False,
        ):
            result = await launcher._probe_cdp("http://127.0.0.1:9222")
            assert result is False

    @pytest.mark.asyncio
    async def test_probe_failure_timeout(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        with patch(
            "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.probe_cdp_endpoint",
            return_value=False,
        ):
            result = await launcher._probe_cdp("http://127.0.0.1:9222")
            assert result is False

    @pytest.mark.asyncio
    async def test_probe_ws_endpoint_uses_tcp(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        with patch(
            "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.probe_cdp_endpoint",
            return_value=True,
        ) as mock_probe:
            result = await launcher._probe_cdp("ws://127.0.0.1:9222/devtools/browser/abc")
            assert result is True
            mock_probe.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser/abc")


# ---------------------------------------------------------------------------
# _connect_existing
# ---------------------------------------------------------------------------


class TestConnectExisting:
    @pytest.mark.asyncio
    async def test_connect_success_returns_unmanaged_instance(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.CONNECT)
        mock_browser = _mock_browser(contexts=2)

        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        launcher._playwright = mock_pw

        inst = await launcher._connect_existing("http://127.0.0.1:9222")

        assert isinstance(inst, BrowserInstance)
        assert inst.is_managed is False
        assert inst.browser is mock_browser
        assert launcher._total_browsers == 1

    @pytest.mark.asyncio
    async def test_connect_failure_raises_after_3_retries(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.CONNECT)

        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(side_effect=ConnectionError("refused"))
        launcher._playwright = mock_pw

        with pytest.raises(BrowserLaunchError, match="after 3 attempts"):
            await launcher._connect_existing("http://127.0.0.1:9222")

        assert mock_pw.chromium.connect_over_cdp.await_count == 3

    @pytest.mark.asyncio
    async def test_connect_retry_succeeds_on_second_attempt(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.CONNECT)
        mock_browser = _mock_browser(contexts=1)

        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(side_effect=[ConnectionError("refused"), mock_browser])
        launcher._playwright = mock_pw

        inst = await launcher._connect_existing("http://127.0.0.1:9222")

        assert inst.is_managed is False
        assert inst.browser is mock_browser
        assert mock_pw.chromium.connect_over_cdp.await_count == 2

    @pytest.mark.asyncio
    async def test_an_empty_header_mapping_reaches_the_driver_as_no_headers(self) -> None:
        """REMOTE mode builds an empty mapping when none are configured, and the driver rejects it as an object."""
        launcher = _make_launcher(launch_mode=LaunchMode.REMOTE)
        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=_mock_browser(contexts=1))
        launcher._playwright = mock_pw

        await launcher._connect_existing("ws://127.0.0.1:9222/devtools/browser/x", headers={})

        mock_pw.chromium.connect_over_cdp.assert_awaited_once_with(
            "ws://127.0.0.1:9222/devtools/browser/x", headers=None
        )

    @pytest.mark.asyncio
    async def test_configured_headers_reach_the_driver_untouched(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.REMOTE)
        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=_mock_browser(contexts=1))
        launcher._playwright = mock_pw
        headers = {"Authorization": "Bearer token"}

        await launcher._connect_existing("ws://127.0.0.1:9222/devtools/browser/x", headers=headers)

        mock_pw.chromium.connect_over_cdp.assert_awaited_once_with(
            "ws://127.0.0.1:9222/devtools/browser/x", headers=headers
        )


# ---------------------------------------------------------------------------
# create_browser routing
# ---------------------------------------------------------------------------


class TestCreateBrowserRouting:
    @pytest.mark.asyncio
    async def test_launch_mode_calls_launch_new(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.LAUNCH)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=True)

        with patch.object(launcher, "_launch_new_browser", AsyncMock(return_value=expected)) as mock_launch:
            result = await launcher.create_browser()

            mock_launch.assert_awaited_once()
            assert result.is_managed is True

    @pytest.mark.asyncio
    async def test_connect_mode_calls_connect_existing(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.CONNECT)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=False)

        with (
            patch.object(launcher, "_discover_local_chrome", AsyncMock(return_value=None)),
            patch.object(launcher, "_connect_existing", AsyncMock(return_value=expected)) as mock_connect,
        ):
            result = await launcher.create_browser()

            mock_connect.assert_awaited_once_with(launcher._cdp_endpoint, headers=None)
            assert result.is_managed is False

    @pytest.mark.asyncio
    async def test_auto_mode_probe_success_connects(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=False)

        with (
            patch.object(launcher, "_probe_cdp", AsyncMock(return_value=True)),
            patch.object(launcher, "_connect_existing", AsyncMock(return_value=expected)) as mock_connect,
            patch.object(launcher, "_launch_new_browser", AsyncMock()) as mock_launch,
        ):
            result = await launcher.create_browser()

            mock_connect.assert_awaited_once()
            mock_launch.assert_not_awaited()
            assert result.is_managed is False

    @pytest.mark.asyncio
    async def test_auto_mode_probe_fail_falls_back_to_launch(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=True)

        with (
            patch.object(launcher, "_probe_cdp", AsyncMock(return_value=False)),
            patch.object(launcher, "_connect_existing", AsyncMock()) as mock_connect,
            patch.object(launcher, "_launch_new_browser", AsyncMock(return_value=expected)) as mock_launch,
        ):
            result = await launcher.create_browser()

            mock_connect.assert_not_awaited()
            mock_launch.assert_awaited_once()
            assert result.is_managed is True

    @pytest.mark.asyncio
    async def test_auto_mode_probe_ok_but_connect_fails_falls_back(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=True)

        with (
            patch.object(launcher, "_probe_cdp", AsyncMock(return_value=True)),
            patch.object(
                launcher,
                "_connect_existing",
                AsyncMock(side_effect=Exception("connect err")),
            ),
            patch.object(launcher, "_launch_new_browser", AsyncMock(return_value=expected)) as mock_launch,
        ):
            result = await launcher.create_browser()

            mock_launch.assert_awaited_once()
            assert result.is_managed is True


# ---------------------------------------------------------------------------
# E2E Chrome binding: never retarget an E2E run at another Chrome
# ---------------------------------------------------------------------------


class TestE2eChromeBinding:
    @pytest.mark.asyncio
    async def test_e2e_bound_run_connects_to_its_own_chrome(self) -> None:
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=False)

        with (
            patch(
                "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.resolve_e2e_cdp_endpoint",
                return_value="http://127.0.0.1:9333",
            ),
            patch.object(launcher, "_probe_cdp", AsyncMock(return_value=True)),
            patch.object(launcher, "_connect_existing", AsyncMock(return_value=expected)) as mock_connect,
            patch.object(launcher, "_discover_local_chrome", AsyncMock()) as mock_discover,
            patch.object(launcher, "_launch_new_browser", AsyncMock()) as mock_launch,
        ):
            result = await launcher.create_browser()

            mock_connect.assert_awaited_once_with("http://127.0.0.1:9333", headers=None)
            mock_discover.assert_not_awaited()
            mock_launch.assert_not_awaited()
            assert result is expected

    @pytest.mark.asyncio
    async def test_e2e_bound_run_refuses_foreign_chrome_and_fresh_launch(self) -> None:
        """Regression: discovery must not silently retarget the run at another Chrome.

        A foreign browser carries a different profile (no E2E auth session, no extension
        bridge), and a fresh launch carries an empty one — both make the run's tools fail
        in ways that read as product bugs. Fail loudly instead.
        """
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)

        with (
            patch(
                "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.resolve_e2e_cdp_endpoint",
                return_value="http://127.0.0.1:9333",
            ),
            patch.object(launcher, "_probe_cdp", AsyncMock(return_value=False)),
            patch.object(launcher, "_discover_local_chrome", AsyncMock()) as mock_discover,
            patch.object(launcher, "_connect_existing", AsyncMock()) as mock_connect,
            patch.object(launcher, "_launch_new_browser", AsyncMock()) as mock_launch,
        ):
            with pytest.raises(BrowserLaunchError, match="refusing"):
                await launcher.create_browser()

            mock_discover.assert_not_awaited()
            mock_connect.assert_not_awaited()
            mock_launch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_e2e_bound_keeps_auto_discovery(self) -> None:
        """Desktop/local flows keep the original AUTO behaviour."""
        launcher = _make_launcher(launch_mode=LaunchMode.AUTO)
        expected = BrowserInstance(browser=_mock_browser(), is_managed=False)

        with (
            patch(
                "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.resolve_e2e_cdp_endpoint",
                return_value=None,
            ),
            patch.object(launcher, "_discover_local_chrome", AsyncMock(return_value="http://127.0.0.1:9222")),
            patch.object(launcher, "_probe_cdp", AsyncMock(return_value=True)),
            patch.object(launcher, "_connect_existing", AsyncMock(return_value=expected)) as mock_connect,
        ):
            result = await launcher.create_browser()

            mock_connect.assert_awaited_once_with("http://127.0.0.1:9222", headers=None)
            assert result is expected
