"""The guard judges an answer against everything the turn did, not against the few calls the loop guard still holds."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard import CompletionGuard, reset_completion_guard
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord
from tests.support.call_records import (
    call,
    lint,
    unit_tests,
    write,
)
from tests.support.completion_guard_harness import LOOP_GUARD_PATCH, make_state, reasons_of

WINDOW = 20  # what the loop guard keeps


def reads(count: int) -> list[CallRecord]:
    return [call("file_read_tool", f"/w/note-{index}.md") for index in range(count)]


def a_tool_step(request: str) -> list[object]:
    """A model turn that calls a tool: the guard sees it, and it is not an attempt to finish."""
    return [
        HumanMessage(content=request),
        AIMessage(content="", tool_calls=[{"name": "file_read_tool", "args": {}, "id": "c1"}]),
    ]


def an_answer(request: str, answer: str) -> list[object]:
    return [HumanMessage(content=request), AIMessage(content=answer)]


class TestTurnLedger:
    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    async def model_turn(self, window: list[CallRecord], messages: list[object]) -> dict[str, object] | None:
        """One ``aafter_model`` call, with ``window`` as the calls the loop guard still holds."""
        with patch(LOOP_GUARD_PATCH) as loop_guard:
            loop_guard.return_value.recorded_calls.return_value = window[-WINDOW:]
            return await self.guard.aafter_model(make_state(messages), None)

    @pytest.mark.asyncio
    async def test_code_written_early_and_never_verified_is_held_back_after_the_window_moved_on(self) -> None:
        edit = write("/w/app.py")
        await self.model_turn([edit], a_tool_step("implement the feature"))

        result = await self.model_turn([edit, *reads(24)], an_answer("implement the feature", "I implemented it."))

        assert reasons_of(result).verification

    @pytest.mark.asyncio
    async def test_evidence_gathered_early_still_answers_a_freshness_demand(self) -> None:
        search = call("web_search_tool", "iphone price")
        question = "What is the latest iPhone price?"
        await self.model_turn([search], a_tool_step(question))

        result = await self.model_turn([search, *reads(24)], an_answer(question, "The latest iPhone starts at $799."))

        assert result is None

    @pytest.mark.asyncio
    async def test_a_verification_that_passed_early_still_covers_the_code_written_before_it(self) -> None:
        await self.model_turn([write("/w/app.py")], a_tool_step("implement the feature"))
        proof = unit_tests()
        await self.model_turn([write("/w/app.py"), proof], a_tool_step("implement the feature"))

        result = await self.model_turn(
            [write("/w/app.py"), proof, *reads(24)], an_answer("implement the feature", "Done, tests pass.")
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_the_same_passing_check_run_again_after_an_edit_is_not_dropped_as_a_duplicate(self) -> None:
        first_run = lint()
        await self.model_turn([first_run], a_tool_step("clean up app.py"))
        edit = write("/w/app.py")
        second_run = lint()  # same command, same output, a later call
        await self.model_turn([first_run, edit], a_tool_step("clean up app.py"))

        result = await self.model_turn(
            [first_run, edit, second_run], an_answer("clean up app.py", "Done, lint is clean.")
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_a_window_the_loop_guard_resets_does_not_forget_what_the_turn_did(self) -> None:
        """A continuation segment starts the loop guard's window afresh; the turn's earlier writes stay on the books."""
        edit = write("/w/app.py")
        await self.model_turn([edit], a_tool_step("implement the feature"))

        result = await self.model_turn([], an_answer("implement the feature", "All finished."))

        assert reasons_of(result).verification
