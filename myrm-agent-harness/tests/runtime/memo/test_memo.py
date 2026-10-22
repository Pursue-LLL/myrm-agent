"""Tests for the model-call memo ledger.

The point of the ledger is that an interrupted turn, replayed, does not pay for the model
twice for the same question. The tests below pin the three things that must never be
confused: the turn, the model and the request.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from myrm_agent_harness.runtime.memo import (
    LlmCallScope,
    MemoLedger,
    MemoStatus,
    begin_memo_call,
    complete_memo_call,
    current_llm_call_scope,
    fail_memo_call,
    llm_call_scope,
    start_memo_call,
)

MESSAGES: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
OTHER_MESSAGES: list[dict[str, object]] = [{"role": "user", "content": "something else"}]


def _ledger(tmpdir: str) -> MemoLedger:
    return MemoLedger(Path(tmpdir) / "memo.sqlite3")


def _scope(ledger: MemoLedger, *, session_id: str = "s1", turn_id: str = "t1") -> LlmCallScope:
    return LlmCallScope(session_id=session_id, turn_id=turn_id, ledger=ledger)


def _record(ledger: MemoLedger, *, model: str = "gpt-x", messages: list[dict[str, object]] | None = None) -> None:
    scope = _scope(ledger)
    attempt = begin_memo_call(scope, model, messages if messages is not None else MESSAGES, {"temperature": 0.7})
    start_memo_call(scope, attempt, model)
    complete_memo_call(scope, attempt, model, {"choices": [{"message": {"content": "hi"}}]})


def test_the_same_call_gets_the_same_key() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        first = _scope(ledger).next_key("gpt-x", MESSAGES, {"temperature": 0.7})
        second = _scope(ledger).next_key("gpt-x", MESSAGES, {"temperature": 0.7})
        assert first.digest == second.digest


def test_a_different_turn_gets_a_different_key() -> None:
    """Two turns of the same session must not read each other's answers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        first = _scope(ledger, turn_id="t1").next_key("gpt-x", MESSAGES)
        second = _scope(ledger, turn_id="t2").next_key("gpt-x", MESSAGES)
        assert first.digest != second.digest


def test_a_different_model_gets_a_different_key() -> None:
    """A failover swaps the model mid-turn; the first model's answer must not answer for it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        first = _scope(ledger).next_key("gpt-x", MESSAGES)
        second = _scope(ledger).next_key("gpt-y", MESSAGES)
        assert first.digest != second.digest


def test_a_different_context_gets_a_different_key() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        first = _scope(ledger).next_key("gpt-x", MESSAGES)
        second = _scope(ledger).next_key("gpt-x", OTHER_MESSAGES)
        assert first.digest != second.digest


def test_a_different_ordinal_gets_a_different_key() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        scope = _scope(ledger)
        assert scope.next_key("gpt-x", MESSAGES).digest != scope.next_key("gpt-x", MESSAGES).digest


def test_parameters_that_do_not_shape_the_answer_do_not_split_the_key() -> None:
    """A logging switch must not make the same call look like a different one."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        first = _scope(ledger).next_key("gpt-x", MESSAGES, {"temperature": 0.7, "verbose": True})
        second = _scope(ledger).next_key("gpt-x", MESSAGES, {"temperature": 0.7})
        assert first.digest == second.digest


def test_the_ledger_records_the_call_before_it_dispatches() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        scope = _scope(ledger)
        attempt = begin_memo_call(scope, "gpt-x", MESSAGES)
        start_memo_call(scope, attempt, "gpt-x")
        entry = ledger.get(attempt.key.digest if attempt.key else "")
        assert entry is not None
        assert entry.status is MemoStatus.STARTED
        assert entry.response is None


def test_a_completed_call_is_replayed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        _record(ledger)
        attempt = begin_memo_call(_scope(ledger), "gpt-x", MESSAGES, {"temperature": 0.7})
        assert attempt.response == {"choices": [{"message": {"content": "hi"}}]}


def test_an_unfinished_call_is_not_replayed() -> None:
    """A crash leaves the row at `started`: the outcome is unknown, so the call runs again."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        scope = _scope(ledger)
        attempt = begin_memo_call(scope, "gpt-x", MESSAGES)
        start_memo_call(scope, attempt, "gpt-x")
        again = begin_memo_call(_scope(ledger), "gpt-x", MESSAGES)
        assert again.response is None


def test_a_failed_call_is_not_replayed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        scope = _scope(ledger)
        attempt = begin_memo_call(scope, "gpt-x", MESSAGES)
        start_memo_call(scope, attempt, "gpt-x")
        fail_memo_call(scope, attempt, "gpt-x", "boom")
        entry = ledger.get(attempt.key.digest if attempt.key else "")
        assert entry is not None
        assert entry.status is MemoStatus.FAILED
        again = begin_memo_call(_scope(ledger), "gpt-x", MESSAGES)
        assert again.response is None


def test_another_turn_does_not_read_the_recorded_answer() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        _record(ledger)
        attempt = begin_memo_call(_scope(ledger, turn_id="t2"), "gpt-x", MESSAGES, {"temperature": 0.7})
        assert attempt.response is None


def test_another_model_does_not_read_the_recorded_answer() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        _record(ledger, model="gpt-x")
        attempt = begin_memo_call(_scope(ledger), "gpt-y", MESSAGES, {"temperature": 0.7})
        assert attempt.response is None


def test_a_huge_answer_is_not_memoised() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        scope = _scope(ledger)
        attempt = begin_memo_call(scope, "gpt-x", MESSAGES)
        start_memo_call(scope, attempt, "gpt-x")
        huge = {"content": "x" * 1_100_000}
        assert ledger.record_completed(attempt.key.digest if attempt.key else "", "gpt-x", huge) is False
        again = begin_memo_call(_scope(ledger), "gpt-x", MESSAGES)
        assert again.response is None


def test_no_scope_means_no_memoisation() -> None:
    assert current_llm_call_scope() is None
    attempt = begin_memo_call(None, "gpt-x", MESSAGES)
    assert attempt.key is None
    assert attempt.response is None


def test_the_scope_is_visible_inside_the_block_and_restored_after_it() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = _ledger(tmpdir)
        scope = _scope(ledger)
        with llm_call_scope(scope) as active:
            assert active is scope
            assert current_llm_call_scope() is scope
        assert current_llm_call_scope() is None


def test_a_broken_ledger_does_not_stop_the_call() -> None:
    """The memo path must never break the agent: a failure degrades to a normal call."""

    class BrokenLedger:
        def get(self, key: str) -> None:
            raise RuntimeError("disk on fire")

        def record_started(self, key: str, model: str) -> None:
            raise RuntimeError("disk on fire")

        def record_completed(self, key: str, model: str, response: dict[str, object]) -> bool:
            raise RuntimeError("disk on fire")

        def record_failed(self, key: str, model: str, error: str) -> None:
            raise RuntimeError("disk on fire")

    scope = LlmCallScope(session_id="s1", turn_id="t1", ledger=BrokenLedger())  # type: ignore[arg-type]
    attempt = begin_memo_call(scope, "gpt-x", MESSAGES)
    assert attempt.key is None
    start_memo_call(scope, attempt, "gpt-x")
    complete_memo_call(scope, attempt, "gpt-x", {"content": "x"})


