"""Unit tests for resolve_notify_target."""

from __future__ import annotations

import pytest

from app.services.agent.outbound_notify import NotifyTarget, resolve_notify_target


@pytest.fixture
def multi_targets() -> tuple[NotifyTarget, ...]:
    return (
        NotifyTarget(channel="telegram", recipient_id="chat_123", label="My Telegram"),
        NotifyTarget(channel="telegram", recipient_id="chat_456", label="Work Group"),
        NotifyTarget(channel="slack", recipient_id="C0123ABCD", label="#devops"),
    )


@pytest.fixture
def single_target() -> tuple[NotifyTarget, ...]:
    return (NotifyTarget(channel="telegram", recipient_id="chat_999", label="Only One"),)


class TestExactMatch:
    def test_exact_channel_and_target(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("telegram", "chat_456", multi_targets)
        assert result is not None
        assert result.recipient_id == "chat_456"
        assert result.label == "Work Group"

    def test_exact_match_not_found(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("telegram", "chat_999", multi_targets)
        assert result is None

    def test_exact_match_wrong_channel(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("discord", "chat_123", multi_targets)
        assert result is None


class TestChannelOnlyMatch:
    def test_first_match_for_channel(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("telegram", "", multi_targets)
        assert result is not None
        assert result.recipient_id == "chat_123"

    def test_channel_not_found(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("discord", "", multi_targets)
        assert result is None

    def test_case_insensitive_fallback(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("Telegram", "", multi_targets)
        assert result is not None
        assert result.channel == "telegram"

    def test_case_insensitive_mixed(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("SLACK", "", multi_targets)
        assert result is not None
        assert result.channel == "slack"


class TestSingleTargetShortcut:
    def test_single_target_no_input(self, single_target: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("", "", single_target)
        assert result is not None
        assert result.recipient_id == "chat_999"

    def test_single_target_with_channel_specified(
        self, single_target: tuple[NotifyTarget, ...]
    ) -> None:
        result = resolve_notify_target("telegram", "", single_target)
        assert result is not None
        assert result.recipient_id == "chat_999"

    def test_single_target_wrong_channel(self, single_target: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("slack", "", single_target)
        assert result is None


    def test_single_target_wrong_target_still_resolves(
        self, single_target: tuple[NotifyTarget, ...]
    ) -> None:
        result = resolve_notify_target("", "wrong-id", single_target)
        assert result is not None
        assert result.recipient_id == "chat_999"


class TestTargetOnlyMatch:
    def test_match_by_recipient_id(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("", "C0123ABCD", multi_targets)
        assert result is not None
        assert result.channel == "slack"

    def test_match_by_label(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("", "#devops", multi_targets)
        assert result is not None
        assert result.channel == "slack"

    def test_no_match(self, multi_targets: tuple[NotifyTarget, ...]) -> None:
        result = resolve_notify_target("", "nonexistent", multi_targets)
        assert result is None


class TestEmptyTargets:
    def test_empty_allowed_returns_none(self) -> None:
        result = resolve_notify_target("telegram", "chat_123", ())
        assert result is None

    def test_empty_all_inputs_returns_none(self) -> None:
        result = resolve_notify_target("", "", ())
        assert result is None
