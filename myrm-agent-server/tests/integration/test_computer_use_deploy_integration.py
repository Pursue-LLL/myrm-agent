"""Integration: computer_use deploy gate end-to-end (real gate logic, env-only boundary).

Critical path uses ``is_computer_use_deploy_supported``, ``strip_deploy_incompatible_builtin_tools``,
``resolve_builtin_tool_flags``, and ``_should_setup_computer_use_tools`` without mocking those functions.
Only ``DEPLOY_MODE`` / ``VISUAL_DESKTOP`` env and deploy caches are toggled at the boundary.
"""

from __future__ import annotations

import pytest

from app.config.computer_use_deploy import (
    clear_vnc_entitlement_cache,
    is_computer_use_deploy_supported,
)
from app.config.deploy_mode import get_deploy_mode
from app.services.agent.builtin_tool_ids import strip_deploy_incompatible_builtin_tools
from app.services.agent.profile_resolver import resolve_builtin_tool_flags


def _reset_deploy_caches() -> None:
    clear_vnc_entitlement_cache()
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()


@pytest.fixture
def sandbox_no_visual_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_deploy_caches()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    monkeypatch.delenv("VISUAL_DESKTOP", raising=False)
    yield
    _reset_deploy_caches()


@pytest.fixture
def sandbox_with_visual_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_deploy_caches()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    monkeypatch.setenv("VISUAL_DESKTOP", "1")
    yield
    _reset_deploy_caches()


@pytest.fixture
def local_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_deploy_caches()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.delenv("VISUAL_DESKTOP", raising=False)
    yield
    _reset_deploy_caches()


@pytest.mark.integration
def test_deploy_gate_false_in_sandbox_without_visual_desktop(
    sandbox_no_visual_desktop: None,
) -> None:
    assert is_computer_use_deploy_supported() is False


@pytest.mark.integration
def test_strip_removes_computer_use_when_sandbox_lacks_visual_desktop(
    sandbox_no_visual_desktop: None,
) -> None:
    stripped = strip_deploy_incompatible_builtin_tools(["web_search", "computer_use", "browser"])
    assert stripped == ["web_search", "browser"]


@pytest.mark.integration
def test_resolve_flags_disable_computer_use_when_sandbox_lacks_visual_desktop(
    sandbox_no_visual_desktop: None,
) -> None:
    flags = resolve_builtin_tool_flags(["computer_use", "browser"])
    assert flags["enable_computer_use"] is False
    assert flags["enable_browser"] is True


@pytest.mark.integration
def test_factory_gate_skips_computer_use_tools_when_deploy_unsupported(
    sandbox_no_visual_desktop: None,
) -> None:
    from app.ai_agents.general_agent.factory import _should_setup_computer_use_tools

    assert _should_setup_computer_use_tools(True) is False
    assert _should_setup_computer_use_tools(False) is False


@pytest.mark.integration
def test_deploy_gate_true_in_sandbox_with_visual_desktop_and_vnc_entitlement(
    sandbox_with_visual_desktop: None,
) -> None:
    from unittest.mock import MagicMock, patch

    clear_vnc_entitlement_cache()
    mock_entitlement = MagicMock()
    mock_entitlement.enable_vnc = True

    with patch(
        "app.platform_utils.sandbox.entitlements.entitlement_guard.fetch_sandbox_entitlements",
        return_value=mock_entitlement,
    ):
        assert is_computer_use_deploy_supported() is True
        flags = resolve_builtin_tool_flags(["computer_use"])
        assert flags["enable_computer_use"] is True


@pytest.mark.integration
def test_deploy_gate_true_in_local_mode(local_deploy: None) -> None:
    assert is_computer_use_deploy_supported() is True
    from app.ai_agents.general_agent.factory import _should_setup_computer_use_tools

    assert _should_setup_computer_use_tools(True) is True
    flags = resolve_builtin_tool_flags(["computer_use", "browser"])
    assert flags["enable_computer_use"] is True


@pytest.mark.integration
def test_external_cli_strip_removed_in_sandbox(sandbox_no_visual_desktop: None) -> None:
    from app.config.external_cli_deploy import is_external_cli_deploy_supported

    assert is_external_cli_deploy_supported() is False
    stripped = strip_deploy_incompatible_builtin_tools(["web_search", "external_cli"])
    assert stripped == ["web_search"]


@pytest.mark.integration
def test_external_cli_kept_in_local_mode(local_deploy: None) -> None:
    from app.config.external_cli_deploy import is_external_cli_deploy_supported

    assert is_external_cli_deploy_supported() is True
    stripped = strip_deploy_incompatible_builtin_tools(["memory", "external_cli"])
    assert stripped == ["memory", "external_cli"]
