"""The grant fields of a decision: which always-allow the person asked for, how long it lasts, and what the card carried."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.approval._batch_decisions import _card_text, apply_approval_decisions

_CALL = {"name": "bash_code_execute_tool", "args": {"command": "ls"}, "id": "c1", "type": "tool_call"}
_ALLOWLIST_WRITE = "myrm_agent_harness.agent.middlewares.approval._batch_decisions.try_add_to_allowlist"


async def _allowlist_write(decision: dict[str, object]) -> tuple[object, object]:
    """Approve the one pending call with *decision*; return the always-allow and TTL handed to the allowlist write."""
    pending = [(0, _CALL, "shell_exec", "needs approval", None)]
    with patch(_ALLOWLIST_WRITE, new_callable=AsyncMock) as write:
        await apply_approval_decisions([decision], AIMessage(content="", tool_calls=[_CALL]), [], pending, [0], {})
    write.assert_awaited_once()
    return write.await_args.args[2], write.await_args.kwargs["ttl_seconds"]


class TestAlwaysAllowGrant:
    @pytest.mark.parametrize(
        ("decision", "grant"),
        [
            ({"type": "approve", "extensions": {"allowAlways": True}}, True),
            ({"type": "approve", "allow_always": True}, True),
            ({"type": "approve", "allowAlways": True}, True),
            ({"type": "approve", "extensions": {"allowAlways": {"tool": True}}}, {"tool": True}),
            ({"type": "approve", "allow_always": {"tool": True, "pattern": True}}, {"tool": True, "pattern": True}),
            ({"type": "edit", "extensions": {"allowAlways": True}}, True),
            ({"type": "approve"}, False),
        ],
        ids=["extension-flag", "flag", "camel-flag", "extension-tool", "tool-pattern", "edit", "nothing-asked"],
    )
    async def test_the_choice_reaches_the_allowlist_write_as_the_person_made_it(
        self, decision: dict[str, object], grant: bool | dict[str, bool]
    ) -> None:
        written, _ = await _allowlist_write(decision)

        assert written == grant
        assert type(written) is type(grant)

    @pytest.mark.parametrize("value", ["yes", 1, ["tool"]], ids=["text", "number", "list"])
    async def test_a_value_that_is_neither_a_flag_nor_a_dict_grants_nothing(self, value: object) -> None:
        written, _ = await _allowlist_write({"type": "approve", "extensions": {"allowAlways": value}})

        assert written is False

    @pytest.mark.parametrize(
        "extensions", [None, "allowAlways", ["allowAlways"], 7], ids=["null", "text", "list", "number"]
    )
    async def test_extensions_that_are_not_a_dict_read_as_no_extensions(self, extensions: object) -> None:
        written, ttl = await _allowlist_write({"type": "approve", "extensions": extensions})

        assert (written, ttl) == (False, None)


class TestAlwaysAllowDuration:
    @pytest.mark.parametrize(
        ("decision", "ttl"),
        [
            ({"type": "approve", "ttl_seconds": 3600}, 3600),
            ({"type": "approve", "ttlSeconds": 60}, 60),
            ({"type": "approve", "extensions": {"ttlSeconds": 30}}, 30),
            ({"type": "approve", "extensions": {"ttl_seconds": -1}}, -1),
            ({"type": "approve", "ttl_seconds": 1.5}, 1.5),
            ({"type": "approve", "ttl_seconds": 5, "ttlSeconds": 9, "extensions": {"ttlSeconds": 1}}, 5),
            ({"type": "approve"}, None),
        ],
        ids=["flat", "camel", "extension", "extension-session", "fraction", "flat-wins", "none"],
    )
    async def test_the_first_duration_the_person_gave_is_the_one_used(
        self, decision: dict[str, object], ttl: float | None
    ) -> None:
        _, written = await _allowlist_write(decision)

        assert written == ttl


class TestCardText:
    def test_a_text_the_card_carried_comes_back_as_text(self) -> None:
        assert _card_text({"action_digest": "abc123"}, "action_digest") == "abc123"

    @pytest.mark.parametrize("extra_ctx", [None, {}, {"action_digest": None}, {"action_digest": ""}])
    def test_a_card_without_the_text_gives_an_empty_one(self, extra_ctx: dict[str, object] | None) -> None:
        assert _card_text(extra_ctx, "action_digest") == ""
