"""Unit tests for desktop approval E2E page transport retry classification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.e2e.desktop_approval.infra_retry import (
    heal_chrome_attach_before_reopen,
    is_retriable_page_transport,
    should_abort_desktop_e2e_retries,
)


def test_detached_frame_is_retriable_not_abort() -> None:
    exc = RuntimeError("Protocol error: detached Frame")
    assert is_retriable_page_transport(exc) is True
    assert should_abort_desktop_e2e_retries(exc) is False


def test_mux_upstream_timeout_is_retriable() -> None:
    exc = RuntimeError(
        "Chrome MCP tools/call error: upstream request timed out after 95000ms"
    )
    assert is_retriable_page_transport(exc) is True


def test_econnrefused_is_abort_not_retriable() -> None:
    exc = ConnectionError("ECONNREFUSED connecting to http://127.0.0.1:8080")
    assert should_abort_desktop_e2e_retries(exc) is True
    assert is_retriable_page_transport(exc) is False


def test_retry_reset_evaluate_timeout_is_retriable() -> None:
    exc = TimeoutError(
        "retry reset evaluate wall-timeout step=click_new_chat timeout=75s"
    )
    assert is_retriable_page_transport(exc) is True


def test_bridge_missing_runtime_error_is_retriable() -> None:
    exc = RuntimeError(
        "Dev E2E chat bridge not available on WebUI during BASIC model pin"
    )
    assert is_retriable_page_transport(exc) is True


def test_no_page_found_runtime_error_is_retriable() -> None:
    exc = RuntimeError("Chrome MCP navigate_page failed: Error: No page found")
    assert is_retriable_page_transport(exc) is True


def test_mux_reclaim_stall_is_retriable() -> None:
    exc = TimeoutError("MUX_RECLAIM_STALL: evaluate orphaned after 25s")
    assert is_retriable_page_transport(exc) is True


def test_connection_reset_during_tools_call_is_retriable_not_abort() -> None:
    exc = RuntimeError(
        "Chrome MCP tools/call error: Chrome MCP connection reset during tools/call; retry this call"
    )
    assert is_retriable_page_transport(exc) is True
    assert should_abort_desktop_e2e_retries(exc) is False


def test_open_mcp_page_timeout_is_retriable() -> None:
    exc = TimeoutError("open_mcp_page wall timeout after 95s")
    assert is_retriable_page_transport(exc) is True


def test_request_lock_wall_budget_exhausted_is_retriable() -> None:
    exc = RuntimeError("request lock wall budget exhausted")
    assert is_retriable_page_transport(exc) is True


@pytest.mark.asyncio
async def test_heal_chrome_attach_skipped_when_boot_mux_gate_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    monkeypatch.setenv("MYRM_E2E_BOOT_MUX_GATE_OK", "1")
    with patch(
        "tests.e2e.desktop_approval.infra_retry.assert_chrome_attach_health"
    ) as attach:
        await heal_chrome_attach_before_reopen()
        attach.assert_not_called()


@pytest.mark.asyncio
async def test_heal_chrome_attach_runs_when_boot_mux_gate_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    monkeypatch.delenv("MYRM_E2E_BOOT_MUX_GATE_OK", raising=False)
    with patch(
        "tests.e2e.desktop_approval.infra_retry.assert_chrome_attach_health"
    ) as attach:
        await heal_chrome_attach_before_reopen()
        attach.assert_called_once()
