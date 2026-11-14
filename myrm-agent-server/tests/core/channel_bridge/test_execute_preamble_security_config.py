"""The security overlay of one channel turn: what that turn's message and query set over the user's saved config."""

from __future__ import annotations

import pytest

from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY
from app.core.channel_bridge.agent_executor.execute_preamble.types import build_security_overlay
from app.core.security.session_overlay import YoloGrant

_CONFIGURED = {"approvalTimeoutSeconds": 120, "approvalTimeoutBehavior": "deny"}
_LEARN_QUERY = '[/learn] The user wants you to learn a reusable skill\n2. Save it with the `skill_manage_tool` (action="save").'


def _config_after(metadata: dict[str, object], base: dict[str, object] | None = _CONFIGURED) -> dict[str, object] | None:
    return build_security_overlay(metadata, "hello").apply(base)


def test_a_turn_without_a_window_keeps_the_configured_one() -> None:
    assert _config_after({}) == _CONFIGURED


def test_a_turn_window_replaces_the_configured_one_and_nothing_else() -> None:
    config = _config_after({METADATA_APPROVAL_WINDOW_SECONDS_KEY: 1800.0})

    assert config == {"approvalTimeoutSeconds": 1800, "approvalTimeoutBehavior": "deny"}


def test_the_configured_dict_is_never_mutated() -> None:
    configured = dict(_CONFIGURED)

    _config_after({METADATA_APPROVAL_WINDOW_SECONDS_KEY: 1800.0, "yolo_state": (1.0, 60)}, configured)

    assert configured == _CONFIGURED


def test_a_turn_window_works_without_any_configured_security() -> None:
    assert _config_after({METADATA_APPROVAL_WINDOW_SECONDS_KEY: 600}, None) == {"approvalTimeoutSeconds": 600}


def test_a_fractional_window_still_waits_at_least_a_second() -> None:
    assert build_security_overlay({METADATA_APPROVAL_WINDOW_SECONDS_KEY: 0.4}, "").approval_window_seconds == 1


@pytest.mark.parametrize("window", [True, False, 0, -5, 0.0, "1800", None, [], {}])
def test_a_window_that_is_not_a_positive_number_is_ignored(window: object) -> None:
    overlay = build_security_overlay({METADATA_APPROVAL_WINDOW_SECONDS_KEY: window}, "")

    assert overlay.approval_window_seconds is None
    assert overlay.apply(_CONFIGURED) == _CONFIGURED


def test_the_window_and_yolo_state_are_both_applied() -> None:
    config = _config_after({METADATA_APPROVAL_WINDOW_SECONDS_KEY: 900, "yolo_state": (1700000000.0, 3600)})

    assert config is not None
    assert config["approvalTimeoutSeconds"] == 900
    assert config["yolo_mode_enabled"] is True
    assert config["yolo_mode_enabled_at"] == 1700000000.0
    assert config["yolo_mode_timeout"] == 3600


def test_a_session_yolo_without_a_time_limit_is_a_grant_without_a_timeout() -> None:
    overlay = build_security_overlay({"yolo_state": (1700000000.0, None)}, "")

    assert overlay.yolo == YoloGrant(enabled_at=1700000000.0, timeout_seconds=None)


@pytest.mark.parametrize(
    "state",
    [None, (), (1.0,), (1.0, 60, 3), [1.0, 60], "yolo", ("now", 60), (1.0, "60"), (1.0, 0), (1.0, -60), (True, 60), (1.0, True)],
)
def test_a_session_yolo_state_that_is_not_a_timestamp_and_a_positive_limit_grants_nothing(state: object) -> None:
    overlay = build_security_overlay({"yolo_state": state}, "")

    assert overlay.yolo is None
    assert overlay.apply(_CONFIGURED) == _CONFIGURED


def test_a_learn_authoring_query_elevates_skill_manage() -> None:
    overlay = build_security_overlay({}, _LEARN_QUERY)

    assert overlay.learn_authoring is True
    config = overlay.apply({"permissions": {"skill_manage": "deny"}})
    assert config == {"permissions": {"skill_manage": "ask"}}


def test_a_learn_authoring_query_made_of_text_blocks_elevates_skill_manage() -> None:
    assert build_security_overlay({}, [{"type": "text", "text": _LEARN_QUERY}]).learn_authoring is True


@pytest.mark.parametrize("query", ["Summarize this document", "", [{"type": "image_url", "image_url": {"url": "x"}}]])
def test_an_ordinary_query_elevates_nothing(query: object) -> None:
    overlay = build_security_overlay({}, query)

    assert overlay.learn_authoring is False
    assert overlay.apply(_CONFIGURED) == _CONFIGURED
