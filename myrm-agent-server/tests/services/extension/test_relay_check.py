"""Tests for the browser Doctor extension relay check.

The check reads the live extension bridge in-process. A real ``ExtensionBridgeService`` is used so the
policy and connection answers come from the production logic; only the CDP relay round trip, the
deploy mode and the auth token are pinned.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.doctor import CheckStatus, DoctorCheckResult
from pydantic import SecretStr

from app.services.extension.bridge import ExtensionBridgeService
from app.services.extension.relay_check import check_extension_relay

_MODULE = "app.services.extension.relay_check"


def _bridge(*, connected: bool = False, allow_all: bool = False) -> ExtensionBridgeService:
    bridge = ExtensionBridgeService()
    bridge._connected = connected
    bridge._allow_all_eligible_tabs = allow_all
    return bridge


async def _run(bridge: ExtensionBridgeService, *, remote: bool = False, token: str = "") -> DoctorCheckResult:
    with (
        patch(f"{_MODULE}.get_extension_bridge", return_value=bridge),
        patch(f"{_MODULE}.is_webui_remote_mode", return_value=remote),
        patch(f"{_MODULE}.settings", SimpleNamespace(extension_auth_token=SecretStr(token))),
    ):
        return await check_extension_relay()


async def test_ready_relay_reports_ok() -> None:
    bridge = _bridge(connected=True, allow_all=True)

    with patch.object(bridge, "relay_cdp_ready", AsyncMock(return_value=True)):
        result = await _run(bridge)

    assert result.name == "extension_relay"
    assert result.status is CheckStatus.OK
    assert result.fix is None


async def test_connected_extension_without_authorized_sites_is_a_real_warning() -> None:
    """Connected but nothing authorized: the relay cannot be ready, and the user must act, so it is not optional."""
    result = await _run(_bridge(connected=True))

    assert result.status is CheckStatus.WARNING
    assert "access policy" in result.message
    assert result.fix is not None
    assert "allow-all" in result.fix
    assert not (result.details or {}).get("optional")


async def test_missing_auth_token_is_a_real_warning_when_the_deploy_mode_requires_one() -> None:
    result = await _run(_bridge(), remote=True, token="")

    assert result.status is CheckStatus.WARNING
    assert "auth token" in result.message
    assert result.fix is not None
    assert "EXTENSION_AUTH_TOKEN" in result.fix
    assert not (result.details or {}).get("optional")


async def test_configured_auth_token_does_not_raise_the_token_warning() -> None:
    result = await _run(_bridge(), remote=True, token="secret")

    assert result.status is CheckStatus.WARNING
    assert "not connected" in result.message
    assert result.details == {"optional": True}


async def test_unconnected_extension_is_an_optional_capability() -> None:
    result = await _run(_bridge())

    assert result.status is CheckStatus.WARNING
    assert "not connected" in result.message
    assert result.fix is not None
    assert result.details == {"optional": True}


async def test_relay_not_ready_despite_valid_policy_is_optional() -> None:
    bridge = _bridge(connected=True, allow_all=True)

    with patch.object(bridge, "relay_cdp_ready", AsyncMock(return_value=False)):
        result = await _run(bridge)

    assert result.status is CheckStatus.WARNING
    assert "CDP relay is not ready" in result.message
    assert result.details == {"optional": True}


@pytest.mark.parametrize("failure", [RuntimeError("boom"), OSError("socket closed")])
async def test_probe_failure_degrades_to_a_visible_warning(failure: Exception) -> None:
    """The Doctor report must still be produced when the relay probe itself breaks."""
    bridge = _bridge(connected=True, allow_all=True)

    with patch.object(bridge, "relay_cdp_ready", AsyncMock(side_effect=failure)):
        result = await _run(bridge)

    assert result.status is CheckStatus.WARNING
    assert "probe failed" in result.message
    assert str(failure) in result.message
    assert not (result.details or {}).get("optional")
