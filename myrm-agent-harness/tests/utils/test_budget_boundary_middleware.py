"""Tests for BudgetBoundaryMiddleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.middlewares._message_origin import is_user_authored_human_message
from myrm_agent_harness.utils.token_economics.budget_boundary_middleware import (
    _HINT_PREFIX,
    BudgetBoundaryMiddleware,
    _build_finalize_hint,
    _build_warning_hint,
)
from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus


def _make_tracker(status: str = "ok", remaining: float | None = 1.0) -> MagicMock:
    tracker = MagicMock()
    tracker.budget_checker = MagicMock()
    tracker.budget_checker.get_remaining_budget.return_value = remaining
    tracker.last_budget_status = status
    return tracker


class TestBuildHints:
    def test_warning_hint_with_remaining(self) -> None:
        hint = _build_warning_hint(0.80)
        assert "$0.80" in hint
        assert "Budget is running low" in hint

    def test_warning_hint_without_remaining(self) -> None:
        hint = _build_warning_hint(None)
        assert "$" not in hint
        assert "Budget is running low" in hint

    def test_finalize_hint_with_remaining(self) -> None:
        hint = _build_finalize_hint(0.12)
        assert "$0.12" in hint
        assert "Budget limit reached" in hint

    def test_finalize_hint_without_remaining(self) -> None:
        hint = _build_finalize_hint(None)
        assert "$" not in hint
        assert "Budget limit reached" in hint


class TestBeforeModel:
    def test_no_op_when_disabled(self) -> None:
        mw = BudgetBoundaryMiddleware(enabled=False)
        result = mw.before_model({"messages": []}, None)
        assert result is None

    def test_no_op_when_no_tracker(self) -> None:
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=None,
        ):
            result = mw.before_model({"messages": []}, None)
            assert result is None

    def test_no_op_when_budget_ok(self) -> None:
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker("ok"),
        ):
            result = mw.before_model({"messages": [HumanMessage(content="hi")]}, None)
            assert result is None

    def test_injects_warning_hint_with_remaining(self) -> None:
        """Hint includes dynamic remaining budget and uses HumanMessage (preserves prompt cache)."""
        mw = BudgetBoundaryMiddleware()
        messages = [HumanMessage(content="hi")]
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.WARNING, remaining=0.80),
        ):
            result = mw.before_model({"messages": messages}, None)
            assert result is not None
            assert len(result["messages"]) == 1
            hint = result["messages"][0]
            assert isinstance(hint, HumanMessage)
            assert "Budget is running low" in hint.content
            assert "$0.80" in hint.content
            assert _HINT_PREFIX in hint.content

    def test_the_hint_is_the_runtimes_message_not_the_users(self) -> None:
        """The input screens act on what the user wrote; the hint is not that, and must not be taken for it."""
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.FINALIZATION, remaining=0.12),
        ):
            result = mw.before_model({"messages": [HumanMessage(content="hi")]}, None)

        assert result is not None
        assert not is_user_authored_human_message(result["messages"][0])

    def test_warning_hint_graceful_when_remaining_none(self) -> None:
        """Hint degrades gracefully when get_remaining_budget() returns None."""
        mw = BudgetBoundaryMiddleware()
        messages = [HumanMessage(content="hi")]
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.WARNING, remaining=None),
        ):
            result = mw.before_model({"messages": messages}, None)
            assert result is not None
            last = result["messages"][-1]
            assert "Budget is running low" in last.content
            assert "$" not in last.content

    def test_warning_hint_idempotent(self) -> None:
        """Re-injection is skipped when a budget hint is already present."""
        mw = BudgetBoundaryMiddleware()
        existing_hint = HumanMessage(content=f"[SYSTEM INSTRUCTION] {_HINT_PREFIX}\n{_build_warning_hint(0.80)}")
        messages = [HumanMessage(content="hi"), existing_hint]
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.WARNING, remaining=0.50),
        ):
            result = mw.before_model({"messages": messages}, None)
            assert result is None

    def test_the_hint_is_not_repeated_however_long_the_run_goes_on(self) -> None:
        """A run is the messages behind the user's latest one: the hint stays in it, many tool rounds back."""
        mw = BudgetBoundaryMiddleware()
        hint = HumanMessage(
            content=f"[SYSTEM INSTRUCTION] {_HINT_PREFIX}\nlow", additional_kwargs={"is_system_synthetic": True}
        )
        rounds = [
            message
            for n in range(6)
            for message in (
                AIMessage(content=f"a{n}"),
                HumanMessage(content=f"t{n}", additional_kwargs={"is_system_synthetic": True}),
            )
        ]
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.WARNING, remaining=0.50),
        ):
            assert mw.before_model({"messages": [HumanMessage(content="hi"), hint, *rounds]}, None) is None

    def test_a_new_user_message_starts_a_run_that_gets_its_own_hint(self) -> None:
        mw = BudgetBoundaryMiddleware()
        hint = HumanMessage(
            content=f"[SYSTEM INSTRUCTION] {_HINT_PREFIX}\nlow", additional_kwargs={"is_system_synthetic": True}
        )
        messages = [HumanMessage(content="first"), hint, AIMessage(content="answer"), HumanMessage(content="second")]
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.WARNING, remaining=0.50),
        ):
            result = mw.before_model({"messages": messages}, None)

        assert result is not None
        assert _HINT_PREFIX in result["messages"][0].content

    def test_injects_finalization_hint_once(self) -> None:
        mw = BudgetBoundaryMiddleware()
        messages = [HumanMessage(content="hi")]
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.FINALIZATION, remaining=0.12),
        ):
            result = mw.before_model({"messages": messages}, None)
            assert result is not None
            last_content = result["messages"][-1].content
            assert "Budget limit reached" in last_content
            assert "$0.12" in last_content

            result2 = mw.before_model({"messages": messages}, None)
            assert result2 is None


class TestAfterModel:
    def test_no_op_when_ok(self) -> None:
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker("ok"),
        ):
            result = mw.after_model({"messages": [AIMessage(content="answer")]}, None)
            assert result is None

    def test_strips_tool_calls_on_finalization(self) -> None:
        mw = BudgetBoundaryMiddleware()
        ai_msg = AIMessage(content="thinking", id="a1")
        ai_msg.tool_calls = [{"name": "search", "args": {}, "id": "tc1"}]  # type: ignore[assignment]

        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.FINALIZATION),
        ):
            result = mw.after_model({"messages": [HumanMessage(content="hi"), ai_msg]}, None)
            assert result is not None
            assert len(result["messages"]) == 1
            patched = result["messages"][0]
            assert isinstance(patched, AIMessage)
            assert patched.id == "a1"
            assert not patched.tool_calls

    def test_no_strip_when_no_tool_calls(self) -> None:
        mw = BudgetBoundaryMiddleware()
        ai_msg = AIMessage(content="done")

        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.EXCEEDED),
        ):
            result = mw.after_model({"messages": [ai_msg]}, None)
            assert result is None

    def test_no_op_when_disabled(self) -> None:
        mw = BudgetBoundaryMiddleware(enabled=False)
        ai_msg = AIMessage(content="x")
        ai_msg.tool_calls = [{"name": "t", "args": {}, "id": "tc"}]  # type: ignore[assignment]
        result = mw.after_model({"messages": [ai_msg]}, None)
        assert result is None

    def test_no_op_when_no_tracker_after_model(self) -> None:
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=None,
        ):
            result = mw.after_model({"messages": [AIMessage(content="x")]}, None)
            assert result is None

    def test_no_op_when_empty_messages_after_model(self) -> None:
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.EXCEEDED),
        ):
            result = mw.after_model({"messages": []}, None)
            assert result is None

    def test_no_op_when_last_msg_not_ai(self) -> None:
        mw = BudgetBoundaryMiddleware()
        with patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=_make_tracker(BudgetStatus.EXCEEDED),
        ):
            result = mw.after_model({"messages": [HumanMessage(content="hi")]}, None)
            assert result is None
