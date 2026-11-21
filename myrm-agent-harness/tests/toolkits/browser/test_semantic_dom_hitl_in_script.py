"""Semantic DOM HITL gate inside a script's plan: a step cannot ask anyone, so a high-risk step stops the script.

Mock LangGraph interrupt only — no real browser or patchright session fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.snapshot.aria_types import RefInfo
from myrm_agent_harness.toolkits.browser.tools.semantic_dom_hitl import (
    ScriptApprovalRequiredError,
    enforce_js_eval_guard,
    enforce_semantic_interaction_guard,
)
from myrm_agent_harness.utils.runtime.user_control import planned_against


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    page = MagicMock()
    page.url = "https://example.com/app"
    session.page = page
    session.get_active_page.return_value = page
    return session


def _ref(role: str = "button", name: str = "Submit") -> RefInfo:
    return RefInfo(role=role, name=name, nth=None)


class TestInsideAScript:
    """A script's step cannot ask anyone: an interrupt would unwind the script and resuming would rerun its earlier
    steps, so the gate refuses a high-risk step with an error that stops the script."""

    @pytest.mark.asyncio
    async def test_a_high_risk_click_stops_the_script_without_asking(self, mock_session: MagicMock) -> None:
        with (
            patch("langgraph.types.interrupt") as mock_interrupt,
            planned_against(0),
            pytest.raises(ScriptApprovalRequiredError, match="Delete Repository") as stopped,
        ):
            await enforce_semantic_interaction_guard(
                session=mock_session,
                tool_name="browser_execute_script_tool",
                action="click",
                ref="e5",
                ref_info=_ref("button", "Delete Repository"),
            )
        mock_interrupt.assert_not_called()
        assert "browser_interact_tool" in str(stopped.value), "the model is told where this step can be asked"

    @pytest.mark.asyncio
    async def test_a_mutating_evaluate_stops_the_script_without_asking(self, mock_session: MagicMock) -> None:
        with (
            patch("langgraph.types.interrupt") as mock_interrupt,
            planned_against(0),
            pytest.raises(ScriptApprovalRequiredError),
        ):
            await enforce_js_eval_guard(
                session=mock_session,
                tool_name="browser_manage_tool",
                expression="document.forms[0].submit()",
            )
        mock_interrupt.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_safe_step_still_runs(self, mock_session: MagicMock) -> None:
        with patch("langgraph.types.interrupt") as mock_interrupt, planned_against(0):
            clicked = await enforce_semantic_interaction_guard(
                session=mock_session,
                tool_name="browser_execute_script_tool",
                action="click",
                ref="e1",
                ref_info=_ref("button", "Search"),
            )
            read = await enforce_js_eval_guard(
                session=mock_session, tool_name="browser_manage_tool", expression="document.title"
            )
        assert clicked is None
        assert read is None
        mock_interrupt.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_refusal_is_audited_as_a_denial(self, mock_session: MagicMock) -> None:
        with (
            patch("langgraph.types.interrupt"),
            patch("myrm_agent_harness.core.security.audit.record_decision") as record,
            planned_against(0),
            pytest.raises(ScriptApprovalRequiredError),
        ):
            await enforce_semantic_interaction_guard(
                session=mock_session,
                tool_name="browser_execute_script_tool",
                action="click",
                ref="e5",
                ref_info=_ref("button", "Delete Repository"),
            )
        record.assert_called_once()
        tool_name, decision, reason = record.call_args.args
        assert (tool_name, decision) == ("browser_execute_script_tool", "DENY")
        assert "Delete Repository" in reason

    @pytest.mark.asyncio
    async def test_outside_a_script_the_same_step_still_asks(self, mock_session: MagicMock) -> None:
        with patch("langgraph.types.interrupt", return_value={"decision": "approve"}) as mock_interrupt:
            result = await enforce_semantic_interaction_guard(
                session=mock_session,
                tool_name="browser_interact_tool",
                action="click",
                ref="e5",
                ref_info=_ref("button", "Delete Repository"),
            )
        assert result is None
        mock_interrupt.assert_called_once()
