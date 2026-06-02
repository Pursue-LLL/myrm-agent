"""End-to-end coverage of the cross-channel reaction approval pipeline.

Verifies the three pillars of the reaction approval contract:

1.  ``parse_approval_command`` recognises the unified three-tier emoji /
    text alphabet (``allow_once`` / ``allow_always`` / ``deny``) including
    skin-tone modifiers and variation selectors.
2.  ``RouterCommandsMixin._is_reaction_approval_valid`` enforces the
    requester / co-approver allow-list in group chats while staying
    permissive in 1:1 DMs.
3.  ``RouterCommandsMixin._handle_approval_command`` translates each tier
    into the harness ``apply_approval_decisions`` payload contract and
    routes the resume message back through the session gate.

These tests exercise the mixin directly with light-weight stubs so the
suite remains fast and deterministic without spinning up a real router.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.commands import (
    ApprovalDecision,
    normalize_approval_emoji,
    parse_approval_command,
)
from app.channels.routing.router_commands import RouterCommandsMixin
from app.channels.routing.router_keys import routing_session_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_active_task(
    requester_id: str = "alice",
    *,
    channel: str = "slack",
    chat_id: str = "C1",
) -> _ActiveTask:
    """Construct a stubbed ``_ActiveTask`` with a benign already-done task."""
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        future.set_result(None)
    finally:
        loop.close()

    return _ActiveTask(
        task=future,  # type: ignore[arg-type]
        cancel_token=MagicMock(),
        channel=channel,
        chat_id=chat_id,
        placeholder_id=None,
        requester_id=requester_id,
    )


@dataclass(slots=True)
class _MixinHost(RouterCommandsMixin):
    """Minimal stub satisfying ``RouterCommandsHost`` for the mixin under test."""

    _active_tasks: dict[str, _ActiveTask] = field(default_factory=dict)
    _approval_msg_ids: dict[str, str] = field(default_factory=dict)
    _approval_co_approvers: frozenset[str] = field(default_factory=frozenset)
    _bus: MagicMock = field(default_factory=MagicMock)
    _gate: MagicMock = field(default_factory=MagicMock)


def _host(**overrides: Any) -> _MixinHost:  # noqa: ANN401
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.edit_channel_message = AsyncMock()
    gate = MagicMock()
    gate.submit = MagicMock()
    return _MixinHost(_bus=bus, _gate=gate, **overrides)


def _reaction(
    *,
    emoji: str = "\U0001F44D",
    sender_id: str = "alice",
    channel: str = "slack",
    chat_id: str = "C1",
    target_message_id: str = "M1",
    is_group: bool = True,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=emoji,
        chat_id=chat_id,
        is_group=is_group,
        message_id=target_message_id,
        metadata={
            "reaction": True,
            "target_message_id": target_message_id,
        },
    )


# ---------------------------------------------------------------------------
# 1. Three-tier emoji vocabulary
# ---------------------------------------------------------------------------


class TestThreeTierVocabulary:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("\U0001F44D", "allow_once"),
            ("\u2705", "allow_once"),
            ("\u2764", "allow_once"),
            ("\u267E\uFE0F", "allow_always"),  # ♾️ with variation selector
            ("\u2B50", "allow_always"),
            ("\U0001F44E", "deny"),
            ("\u274C", "deny"),
            ("\U0001F6AB", "deny"),
        ],
    )
    def test_recognised_emojis(
        self, raw: str, expected: ApprovalDecision
    ) -> None:
        assert parse_approval_command(raw) == expected

    def test_skin_tone_modifier_is_stripped(self) -> None:
        assert parse_approval_command("\U0001F44D\U0001F3FE") == "allow_once"

    def test_variation_selector_is_stripped(self) -> None:
        assert parse_approval_command("\u267E\uFE0F") == "allow_always"

    def test_unknown_emoji_returns_none(self) -> None:
        assert parse_approval_command("\U0001F389") is None  # 🎉

    def test_normalize_helper_is_idempotent(self) -> None:
        emoji = "\U0001F44D\U0001F3FE\uFE0F"
        once = normalize_approval_emoji(emoji)
        twice = normalize_approval_emoji(once)
        assert once == twice == "\U0001F44D"


# ---------------------------------------------------------------------------
# 2. Sender authorisation in `_is_reaction_approval_valid`
# ---------------------------------------------------------------------------


class TestReactionAuthorisation:
    def _setup(self, *, co_approvers: frozenset[str] = frozenset()) -> _MixinHost:
        host = _host(_approval_co_approvers=co_approvers)
        key = routing_session_key("slack", "C1")
        host._active_tasks[key] = _make_active_task("alice")
        host._approval_msg_ids[key] = "M1"
        return host

    def test_dm_bypasses_sender_check(self) -> None:
        host = self._setup()
        msg = _reaction(sender_id="bob", is_group=False)
        assert host._is_reaction_approval_valid(msg) is True

    def test_group_requester_is_allowed(self) -> None:
        host = self._setup()
        msg = _reaction(sender_id="alice")
        assert host._is_reaction_approval_valid(msg) is True

    def test_group_bystander_is_denied(self) -> None:
        host = self._setup()
        msg = _reaction(sender_id="bob")
        assert host._is_reaction_approval_valid(msg) is False

    def test_group_co_approver_is_allowed(self) -> None:
        host = self._setup(co_approvers=frozenset({"oncall"}))
        msg = _reaction(sender_id="oncall")
        assert host._is_reaction_approval_valid(msg) is True

    def test_target_message_mismatch_is_denied(self) -> None:
        host = self._setup()
        msg = _reaction(sender_id="alice", target_message_id="OTHER")
        assert host._is_reaction_approval_valid(msg) is False

    def test_no_active_task_is_denied(self) -> None:
        host = _host()
        msg = _reaction(sender_id="alice")
        assert host._is_reaction_approval_valid(msg) is False

    def test_empty_sender_is_denied(self) -> None:
        host = self._setup()
        msg = _reaction(sender_id="")
        assert host._is_reaction_approval_valid(msg) is False


# ---------------------------------------------------------------------------
# 3. `_handle_approval_command` resume payload contract
# ---------------------------------------------------------------------------


class TestHandleApprovalContract:
    def _setup(self) -> tuple[_MixinHost, InboundMessage]:
        host = _host()
        key = routing_session_key("slack", "C1")
        host._active_tasks[key] = _make_active_task("alice")
        host._approval_msg_ids[key] = "MSGID"
        msg = _reaction(sender_id="alice")
        return host, msg

    @pytest.mark.asyncio
    async def test_allow_once_payload(self) -> None:
        host, msg = self._setup()
        await host._handle_approval_command(msg, "allow_once")
        host._gate.submit.assert_called_once()
        resume = host._gate.submit.call_args[0][0].resume_value
        assert resume == {"decisions": [{"type": "approve"}]}

    @pytest.mark.asyncio
    async def test_allow_always_payload_has_camelcase_extension(self) -> None:
        host, msg = self._setup()
        await host._handle_approval_command(msg, "allow_always")
        resume = host._gate.submit.call_args[0][0].resume_value
        assert resume == {
            "decisions": [
                {"type": "approve", "extensions": {"allowAlways": True}},
            ]
        }

    @pytest.mark.asyncio
    async def test_deny_payload_includes_feedback(self) -> None:
        host, msg = self._setup()
        await host._handle_approval_command(msg, "deny")
        resume = host._gate.submit.call_args[0][0].resume_value
        decisions = resume["decisions"]
        assert decisions[0]["type"] == "reject"
        assert "Denied via slack" in decisions[0]["feedback"]

    @pytest.mark.asyncio
    async def test_batch_mixed_decisions(self) -> None:
        host, msg = self._setup()
        await host._handle_approval_command(
            msg, ["allow_once", "allow_always", "deny"]
        )
        resume = host._gate.submit.call_args[0][0].resume_value
        types = [d["type"] for d in resume["decisions"]]
        assert types == ["approve", "approve", "reject"]
        assert resume["decisions"][1]["extensions"] == {"allowAlways": True}

    @pytest.mark.asyncio
    async def test_no_pending_approval_replies_and_skips_gate(self) -> None:
        host = _host()
        msg = _reaction(sender_id="alice")
        await host._handle_approval_command(msg, "allow_once")
        host._bus.publish_outbound.assert_awaited_once()
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_message_is_consumed_on_handle(self) -> None:
        host, msg = self._setup()
        key = routing_session_key("slack", "C1")
        await host._handle_approval_command(msg, "allow_once")
        assert key not in host._approval_msg_ids
        host._bus.edit_channel_message.assert_awaited_once()
