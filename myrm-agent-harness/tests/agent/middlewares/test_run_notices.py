"""Run-scoped notice memory: a notice keeps its text, or its place, for the whole run."""

from __future__ import annotations

import itertools
import json
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares._run_notices import (
    NoticeLedger,
    frozen_for_run,
    last_stored_message,
    run_scope,
)
from myrm_agent_harness.core.message_origin import is_user_authored_human_message, runtime_human_message


def _request(context: object | None) -> ModelRequest:
    runtime = None if context is None else Runtime(context=context)
    return ModelRequest(model=AsyncMock(), messages=[HumanMessage(content="hi")], runtime=runtime)


class TestRunScope:
    def test_it_is_the_run_context_itself(self) -> None:
        context: dict[str, object] = {"chat_id": "c1"}

        assert run_scope(_request(context)) is context

    def test_a_request_without_a_runtime_has_no_scope(self) -> None:
        assert run_scope(_request(None)) is None

    def test_a_context_that_is_not_a_dict_is_no_scope(self) -> None:
        assert run_scope(_request("not a dict")) is None


class TestFrozenForRun:
    @pytest.mark.asyncio
    async def test_the_first_rendering_is_the_one_every_later_request_gets(self) -> None:
        scope: dict[str, object] = {}
        renderings = iter(["first", "second"])

        async def render() -> str | None:
            return next(renderings)

        assert await frozen_for_run(scope, "k", render) == "first"
        assert await frozen_for_run(scope, "k", render) == "first"

    @pytest.mark.asyncio
    async def test_a_notice_that_was_absent_stays_absent(self) -> None:
        scope: dict[str, object] = {}
        renderings = iter([None, "appears later"])

        async def render() -> str | None:
            return next(renderings)

        assert await frozen_for_run(scope, "k", render) is None
        assert await frozen_for_run(scope, "k", render) is None

    @pytest.mark.asyncio
    async def test_keys_do_not_share_a_memory(self) -> None:
        scope: dict[str, object] = {}

        async def one() -> str | None:
            return "one"

        async def two() -> str | None:
            return "two"

        assert await frozen_for_run(scope, "a", one) == "one"
        assert await frozen_for_run(scope, "b", two) == "two"

    @pytest.mark.asyncio
    async def test_without_a_run_scope_the_notice_is_rendered_every_time(self) -> None:
        renderings = iter(["first", "second"])

        async def render() -> str | None:
            return next(renderings)

        assert await frozen_for_run(None, "k", render) == "first"
        assert await frozen_for_run(None, "k", render) == "second"

    @pytest.mark.asyncio
    async def test_a_new_run_scope_renders_again(self) -> None:
        renderings = iter(["run one", "run two"])

        async def render() -> str | None:
            return next(renderings)

        assert await frozen_for_run({}, "k", render) == "run one"
        assert await frozen_for_run({}, "k", render) == "run two"


def _history() -> list[AnyMessage]:
    return [
        HumanMessage(content="go", id="u1"),
        AIMessage(content="", id="a1", tool_calls=[{"id": "c1", "name": "t", "args": {}}]),
        ToolMessage(content="result", id="t1", tool_call_id="c1"),
    ]


class TestLastStoredMessage:
    def test_it_is_the_newest_message_that_carries_an_id(self) -> None:
        messages = [*_history(), runtime_human_message("request-local notice")]

        assert last_stored_message(messages) is messages[2]

    def test_a_request_without_a_stored_message_has_none(self) -> None:
        assert last_stored_message([HumanMessage(content="no id")]) is None
        assert last_stored_message([]) is None


class TestNoticeLedger:
    def test_a_ledger_with_nothing_written_changes_nothing(self) -> None:
        messages = _history()

        placed = NoticeLedger.of({}, "k").placed_in(messages)

        assert placed == messages
        assert placed is not messages

    def test_a_notice_stands_right_behind_its_anchor(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(_history()[2], "constraint")

        placed = ledger.placed_in(_history())

        assert [m.content for m in placed] == ["go", "", "result", "constraint"]

    def test_a_notice_keeps_its_place_as_the_history_grows(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(_history()[1], "constraint")
        grown = [*_history(), AIMessage(content="more", id="a2")]

        placed = ledger.placed_in(grown)

        assert [m.content for m in placed] == ["go", "", "constraint", "result", "more"]

    def test_every_request_extends_the_one_before(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        history = _history()
        views = [ledger.placed_in(history)]
        ledger.record(history[-1], "first")
        history.append(AIMessage(content="step", id="a2"))
        views.append(ledger.placed_in(history))
        history.append(HumanMessage(content="later", id="h2"))
        ledger.record(history[-1], "second")
        views.append(ledger.placed_in(history))

        for earlier, later in itertools.pairwise(views):
            assert later[: len(earlier)] == earlier

    def test_notices_behind_one_anchor_keep_the_order_they_were_written_in(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(_history()[2], "first")
        ledger.record(_history()[2], "second")

        assert [m.content for m in ledger.placed_in(_history())][-2:] == ["first", "second"]

    def test_a_notice_whose_anchor_is_gone_goes_to_the_end(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(HumanMessage(content="dropped", id="gone"), "constraint")

        assert ledger.placed_in(_history())[-1].content == "constraint"

    def test_a_notice_without_an_anchor_message_goes_to_the_end(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(None, "constraint")
        ledger.record(HumanMessage(content="no id"), "second")

        assert [m.content for m in ledger.placed_in(_history())][-2:] == ["constraint", "second"]

    def test_the_notice_that_already_stands_last_behind_an_anchor_is_not_written_twice(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(_history()[2], "constraint")
        ledger.record(_history()[2], "constraint")

        assert [m.content for m in ledger.placed_in(_history())] == ["go", "", "result", "constraint"]

    def test_the_same_text_behind_another_anchor_is_another_notice(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(_history()[1], "constraint")
        ledger.record(_history()[2], "constraint")

        assert [m.content for m in ledger.placed_in(_history())] == ["go", "", "constraint", "result", "constraint"]

    def test_only_the_newest_notice_is_compared_when_a_notice_is_written(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        for text in ("first", "second", "first"):
            ledger.record(_history()[2], text)

        assert [m.content for m in ledger.placed_in(_history())][-3:] == ["first", "second", "first"]

    def test_the_notices_are_written_by_the_runtime_not_the_user(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        ledger.record(_history()[2], "constraint")

        notice = ledger.placed_in(_history())[-1]

        assert isinstance(notice, HumanMessage)
        assert not is_user_authored_human_message(notice)

    def test_the_input_messages_are_left_alone(self) -> None:
        messages = _history()
        ledger = NoticeLedger.of({}, "k")
        ledger.record(messages[2], "constraint")

        ledger.placed_in(messages)

        assert len(messages) == 3

    def test_the_latest_text_is_the_newest_notice(self) -> None:
        ledger = NoticeLedger.of({}, "k")
        assert ledger.latest_text() is None
        ledger.record(None, "first")
        ledger.record(None, "second")

        assert ledger.latest_text() == "second"

    def test_the_run_scope_holds_the_ledger_as_plain_json(self) -> None:
        scope: dict[str, object] = {}
        NoticeLedger.of(scope, "k").record(_history()[2], "constraint")

        assert json.loads(json.dumps(scope)) == {"k": [["t1", "constraint"]]}
        assert NoticeLedger.of(scope, "k").latest_text() == "constraint"

    def test_a_ledger_without_a_run_scope_forgets_everything_between_requests(self) -> None:
        NoticeLedger.of(None, "k").record(_history()[2], "constraint")

        assert NoticeLedger.of(None, "k").latest_text() is None
