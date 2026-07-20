"""Unit tests for desktop approval E2E page transport retry classification."""

from __future__ import annotations

from tests.e2e.desktop_approval.infra_retry import (
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
