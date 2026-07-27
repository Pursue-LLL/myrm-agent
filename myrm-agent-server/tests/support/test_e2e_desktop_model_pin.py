"""Unit tests for desktop E2E BASIC model pin helpers."""

from __future__ import annotations

import pytest

from tests.support.e2e_desktop_model_pin import (
    _is_transient_provider_pin_error,
    ensure_desktop_basic_model_pinned_for_send,
    expected_desktop_e2e_model,
    ui_provider_debug_matches_expected,
    ui_selection_from_provider_debug,
)


def test_ui_selection_prefers_selection_over_agent_model() -> None:
    debug = {
        "selection": {"providerId": "openai-like", "model": "mimo-v2.5-pro"},
        "agentModelSelection": {"providerId": "minimax", "model": "MiniMax-M3"},
        "primary": {"providerId": "openai-like", "model": "mimo-v2.5-pro"},
    }
    assert ui_selection_from_provider_debug(debug) == {
        "providerId": "openai-like",
        "model": "mimo-v2.5-pro",
    }


def test_ui_selection_mismatch_detects_lite_pollution() -> None:
    expected = expected_desktop_e2e_model()
    debug = {
        "selection": {"providerId": "minimax", "model": "MiniMax-M3"},
        "agentModelSelection": {"providerId": "minimax", "model": "MiniMax-M3"},
        "primary": {"providerId": "openai-like", "model": expected["model"]},
    }
    assert ui_provider_debug_matches_expected(debug) is False


def test_ui_selection_matches_expected_basic_model() -> None:
    expected = expected_desktop_e2e_model()
    debug = {
        "selection": {"providerId": expected["providerId"], "model": expected["model"]},
        "agentModelSelection": {
            "providerId": expected["providerId"],
            "model": expected["model"],
        },
    }
    assert ui_provider_debug_matches_expected(debug) is True


def test_transient_provider_pin_error_detection() -> None:
    assert (
        _is_transient_provider_pin_error(
            "Chrome MCP evaluate_script failed: Error: e2e-send-not-ready-after-provider-init"
        )
        is True
    )
    assert _is_transient_provider_pin_error("transport closed while tools/call") is True
    assert _is_transient_provider_pin_error("model pin payload mismatch") is False


class _PinRetryChat:
    def __init__(self, scripted_results: list[object | BaseException]) -> None:
        self._scripted_results = scripted_results
        self._index = 0
        self.recover_calls = 0

    async def evaluate(
        self,
        _: str,
        *,
        await_promise: bool,
        recv_timeout: float,
    ) -> object:
        _ = await_promise
        _ = recv_timeout
        if self._index >= len(self._scripted_results):
            raise AssertionError("evaluate called more times than scripted")
        result = self._scripted_results[self._index]
        self._index += 1
        if isinstance(result, BaseException):
            raise result
        return result

    async def ensure_chat_surface(self, _: str, *, timeout_sec: float) -> None:
        _ = timeout_sec
        self.recover_calls += 1

    async def ensure_react_e2e_bridge(self, *, timeout_sec: float) -> None:
        _ = timeout_sec
        self.recover_calls += 1


@pytest.mark.asyncio
async def test_pin_for_send_retries_transient_provider_init_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tests.support.e2e_desktop_model_pin.expected_desktop_e2e_model",
        lambda: {"providerId": "openai-like", "model": "agnes-2.0-flash"},
    )
    chat = _PinRetryChat(
        [
            {},
            RuntimeError("e2e-send-not-ready-after-provider-init"),
            {},
            {},
            {"ok": True, "pinned": {"providerId": "openai-like", "model": "agnes-2.0-flash"}},
            {"selection": {"providerId": "openai-like", "model": "agnes-2.0-flash"}},
        ]
    )
    result = await ensure_desktop_basic_model_pinned_for_send(
        chat,
        max_attempts=3,
        retry_sleep_sec=0.0,
    )
    assert result["ok"] is True
    assert result["attempt"] == 2
    assert chat.recover_calls >= 2


@pytest.mark.asyncio
async def test_pin_for_send_escalates_bridge_missing_as_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tests.support.e2e_desktop_model_pin.expected_desktop_e2e_model",
        lambda: {"providerId": "openai-like", "model": "agnes-2.0-flash"},
    )
    chat = _PinRetryChat(
        [
            {},
            {"ok": False, "err": "no-bridge"},
            {},
            {},
            {"ok": False, "err": "no-bridge"},
            {},
        ]
    )
    with pytest.raises(RuntimeError, match="Dev E2E chat bridge not available on WebUI"):
        await ensure_desktop_basic_model_pinned_for_send(
            chat,
            max_attempts=2,
            retry_sleep_sec=0.0,
        )
