"""RecordedLlmFunc tells a silent model from one that answered, without hiding either."""

import pytest

from tests.support.recorded_llm_func import LlmFunc, RecordedLlmFunc


async def _echo(system: str, prompt: str) -> str:
    return f"ok:{system}:{prompt}"


async def _blank(system: str, prompt: str) -> str:
    return "  \n"


async def _raise_timeout(system: str, prompt: str) -> str:
    raise TimeoutError("provider timed out")


def _fail_once_then_answer() -> LlmFunc:
    outcomes: list[Exception | str] = [TimeoutError("first call failed"), "second answer"]

    async def flaky(system: str, prompt: str) -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return flaky


class TestRecordedLlmFunc:
    async def test_it_passes_the_reply_through_and_counts_as_answered(self) -> None:
        recorded = RecordedLlmFunc(_echo)

        assert await recorded("sys", "ask") == "ok:sys:ask"

        assert recorded.replies == ["ok:sys:ask"]
        assert recorded.answered
        recorded.require_answer()

    async def test_a_failing_model_call_still_raises_and_is_no_answer(self) -> None:
        recorded = RecordedLlmFunc(_raise_timeout)

        with pytest.raises(TimeoutError):
            await recorded("sys", "ask")

        assert not recorded.answered
        with pytest.raises(AssertionError, match="provider timed out"):
            recorded.require_answer()

    async def test_a_blank_reply_is_no_answer(self) -> None:
        recorded = RecordedLlmFunc(_blank)

        await recorded("", "ask")

        assert recorded.replies == ["  \n"]
        assert not recorded.answered

    async def test_a_model_that_was_never_called_is_no_answer(self) -> None:
        recorded = RecordedLlmFunc(_echo)

        assert not recorded.answered
        with pytest.raises(AssertionError, match="no reply"):
            recorded.require_answer()

    async def test_one_answer_after_a_failure_counts(self) -> None:
        recorded = RecordedLlmFunc(_fail_once_then_answer())

        with pytest.raises(TimeoutError):
            await recorded("", "one")
        assert await recorded("", "two") == "second answer"

        assert recorded.answered
        recorded.require_answer()
