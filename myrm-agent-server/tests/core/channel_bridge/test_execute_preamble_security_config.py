"""The security config of one channel turn: the user's config, plus what that turn's message sets."""

from __future__ import annotations

import pytest

from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY
from app.core.channel_bridge.agent_executor.execute_preamble.types import build_security_config

_CONFIGURED = {"approvalTimeoutSeconds": 120, "approvalTimeoutBehavior": "deny"}


def test_a_turn_without_a_window_keeps_the_configured_one() -> None:
    config = build_security_config(_CONFIGURED, {})

    assert config == _CONFIGURED


def test_a_turn_window_replaces_the_configured_one_and_nothing_else() -> None:
    config = build_security_config(_CONFIGURED, {METADATA_APPROVAL_WINDOW_SECONDS_KEY: 1800.0})

    assert config == {"approvalTimeoutSeconds": 1800, "approvalTimeoutBehavior": "deny"}


def test_the_configured_dict_is_never_mutated() -> None:
    configured = dict(_CONFIGURED)

    build_security_config(configured, {METADATA_APPROVAL_WINDOW_SECONDS_KEY: 1800.0})

    assert configured == _CONFIGURED


def test_a_turn_window_works_without_any_configured_security() -> None:
    assert build_security_config(None, {METADATA_APPROVAL_WINDOW_SECONDS_KEY: 600}) == {"approvalTimeoutSeconds": 600}


@pytest.mark.parametrize("window", [True, False, 0, -5, 0.0, "1800", None, [], {}])
def test_a_window_that_is_not_a_positive_number_is_ignored(window: object) -> None:
    assert build_security_config(_CONFIGURED, {METADATA_APPROVAL_WINDOW_SECONDS_KEY: window}) == _CONFIGURED


def test_the_window_and_yolo_state_are_both_applied() -> None:
    config = build_security_config(
        _CONFIGURED,
        {METADATA_APPROVAL_WINDOW_SECONDS_KEY: 900, "yolo_state": (1700000000.0, 3600)},
    )

    assert config["approvalTimeoutSeconds"] == 900
    assert config["yolo_mode_enabled"] is True
    assert config["yolo_mode_enabled_at"] == 1700000000.0
    assert config["yolo_mode_timeout"] == 3600
