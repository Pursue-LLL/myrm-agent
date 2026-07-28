"""Unit tests for desktop approval E2E page transport retry classification."""

from __future__ import annotations

import pytest

from tests.e2e.desktop_approval.infra_retry import (
    _resolve_open_nav_wall_timeout_sec,
    is_retriable_page_transport,
    should_abort_desktop_e2e_retries,
)


def test_detached_frame_is_retriable_not_abort() -> None:
    exc = RuntimeError("Protocol error: detached Frame")
    assert is_retriable_page_transport(exc) is True
    assert should_abort_desktop_e2e_retries(exc) is False


def test_mux_upstream_timeout_is_retriable() -> None:
    exc = RuntimeError("Chrome MCP tools/call error: upstream request timed out after 95000ms")
    assert is_retriable_page_transport(exc) is True


def test_econnrefused_is_abort_not_retriable() -> None:
    exc = ConnectionError("ECONNREFUSED connecting to http://127.0.0.1:8080")
    assert should_abort_desktop_e2e_retries(exc) is True
    assert is_retriable_page_transport(exc) is False


def test_retry_reset_evaluate_timeout_is_retriable() -> None:
    exc = TimeoutError("retry reset evaluate wall-timeout step=click_new_chat timeout=75s")
    assert is_retriable_page_transport(exc) is True


def test_bridge_missing_runtime_error_is_retriable() -> None:
    exc = RuntimeError("Dev E2E chat bridge not available on WebUI during BASIC model pin")
    assert is_retriable_page_transport(exc) is True


def test_no_page_found_runtime_error_is_retriable() -> None:
    exc = RuntimeError("Chrome MCP navigate_page failed: Error: No page found")
    assert is_retriable_page_transport(exc) is True


def test_signoff_open_nav_wall_timeout_extended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("E2E_SIGNOFF", raising=False)
    assert _resolve_open_nav_wall_timeout_sec() == 70.0
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    assert _resolve_open_nav_wall_timeout_sec() == 180.0
