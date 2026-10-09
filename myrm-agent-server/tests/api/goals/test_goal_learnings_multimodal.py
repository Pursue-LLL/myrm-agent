"""Goal learnings extraction reads words only: attachments and tool screenshots never reach the prompt."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from myrm_agent_harness.agent.goals.types import GoalExecutionSummary

from app.ai_agents.general_agent.goal_learnings import build_goal_terminal_callback

_DATA_URL = "data:image/png;base64," + "iVBORw0KGgo" * 5000
_IMAGE_BLOCK = {"type": "image_url", "image_url": {"url": _DATA_URL}}
_SUMMARY = GoalExecutionSummary(
    files_modified=(),
    verifications=(),
    browser_checks=0,
    total_tokens=100,
    total_cost_usd=0.01,
    execution_duration_s=5.0,
    turns_used=2,
)


def _goal(goal_id: str, objective: str) -> MagicMock:
    goal = MagicMock()
    goal.goal_id = goal_id
    goal.objective = objective
    goal.session_id = f"session-{goal_id}"
    return goal


@pytest.mark.asyncio
async def test_callback_feeds_only_text_when_messages_carry_screenshots() -> None:
    messages = [
        HumanMessage(content=[{"type": "text", "text": "Fix the login bug"}, _IMAGE_BLOCK]),
        AIMessage(content="On it"),
        ToolMessage(content=[_IMAGE_BLOCK], tool_call_id="t1"),
        HumanMessage(content="Also add tests"),
        AIMessage(content="Done"),
    ]

    with (
        patch("myrm_agent_harness.api.hooks.create_extraction_llm_func"),
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_goal_learnings",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_extract,
    ):
        callback = build_goal_terminal_callback(AsyncMock(), MagicMock())
        await callback(_goal("img", "Fix the login bug"), messages, _SUMMARY)

    assert mock_extract.call_args.kwargs["messages"] == [
        {"role": "user", "content": "Fix the login bug"},
        {"role": "assistant", "content": "On it"},
        {"role": "user", "content": "Also add tests"},
        {"role": "assistant", "content": "Done"},
    ]


@pytest.mark.asyncio
async def test_callback_skips_when_only_attachments_pad_the_message_count() -> None:
    """Messages without any text are not learnable turns and must not satisfy the minimum-turn threshold."""
    messages = [
        HumanMessage(content=[_IMAGE_BLOCK]),
        AIMessage(content="It shows a rising trend"),
        HumanMessage(content=[_IMAGE_BLOCK]),
    ]

    with (
        patch("myrm_agent_harness.api.hooks.create_extraction_llm_func"),
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_goal_learnings",
            new_callable=AsyncMock,
        ) as mock_extract,
    ):
        callback = build_goal_terminal_callback(AsyncMock(), MagicMock())
        await callback(_goal("img-only", "Describe the chart"), messages, _SUMMARY)

    mock_extract.assert_not_called()
