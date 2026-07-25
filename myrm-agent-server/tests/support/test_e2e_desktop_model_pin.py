"""Unit tests for desktop E2E BASIC model pin helpers."""

from __future__ import annotations

from tests.support.e2e_desktop_model_pin import (
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
