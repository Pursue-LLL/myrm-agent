"""Unit tests for file_write LIVE post-send stall scaling (R134)."""

from __future__ import annotations

import pytest

from tests.e2e import test_file_write_empty_chrome_e2e as mod


def test_live_empty_write_post_send_stall_cap_scales_with_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "_parallel_live_agent_peer_count", lambda: 0)
    assert mod._live_empty_write_post_send_stall_cap_sec() == 90.0
    assert mod._live_empty_write_post_steer_idle_cap_sec() == 90.0

    monkeypatch.setattr(mod, "_parallel_live_agent_peer_count", lambda: 4)
    assert mod._live_empty_write_post_send_stall_cap_sec() == 130.0
    assert mod._live_empty_write_post_steer_idle_cap_sec() == 130.0

    monkeypatch.setattr(mod, "_parallel_live_agent_peer_count", lambda: 3)
    assert mod._live_empty_write_post_steer_idle_cap_sec() == 130.0

    monkeypatch.setattr(mod, "_parallel_live_agent_peer_count", lambda: 8)
    assert mod._live_empty_write_post_send_stall_cap_sec() == 150.0
    assert mod._live_empty_write_post_steer_idle_cap_sec() == 150.0
    assert mod._live_bridge_ready_timeout_sec() == 150.0


def test_transport_retryable_rejects_business_failures() -> None:
    assert mod._is_transport_retryable(AssertionError("E2E_STALL: live empty write")) is False
    assert mod._is_transport_retryable(AssertionError("LLM idle without file_write_tool")) is False
    assert mod._is_transport_retryable(TimeoutError("Dev E2E chat bridge not available")) is True
    assert mod._is_transport_retryable(RuntimeError("MUX reclaim stall")) is True
