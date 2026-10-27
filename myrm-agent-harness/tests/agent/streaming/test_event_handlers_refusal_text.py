"""The step a person sees for a refused tool call shows the reason, not the notes that instruct the model."""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.middlewares.approval.denial_diagnostic_bridge import build_auto_review_denial_message
from myrm_agent_harness.agent.middlewares.approval.refusal import DenialCause, denial_hint, rejection_message
from myrm_agent_harness.agent.streaming.event_handlers import _handle_tool_result


async def _error_step(content: str) -> dict:
    msg = ToolMessage(content=content, name="step", tool_call_id="c1", status="error")
    return await anext(_handle_tool_result(msg, "m1", None))


@pytest.mark.asyncio
async def test_a_user_refusal_shows_their_reason_only() -> None:
    reason = rejection_message("use a dry run", timed_out=False)
    content = reason + denial_hint(DenialCause.USER, "none", 0, 3, unattended=False)

    step = await _error_step(content)

    assert step["error"] == reason
    assert "[System:" not in step["error"]


@pytest.mark.asyncio
async def test_a_policy_denial_shows_the_reason_without_its_diagnostic() -> None:
    hint = denial_hint(DenialCause.POLICY, "none", 0, 3, unattended=False)
    content = build_auto_review_denial_message("bash_code_execute_tool", "rm -rf is not allowed", hint)

    step = await _error_step(content)

    assert step["error"] == "Tool execution denied by security policy: rm -rf is not allowed"


@pytest.mark.asyncio
async def test_an_ordinary_tool_error_is_shown_whole() -> None:
    step = await _error_step("ToolExecutionError: disk full")

    assert step["error"] == "ToolExecutionError: disk full"


@pytest.mark.asyncio
async def test_a_result_that_opens_with_a_note_still_shows_a_reason() -> None:
    step = await _error_step("\n\n[System: Stop.]")

    assert step["error"] == "Unknown error"
