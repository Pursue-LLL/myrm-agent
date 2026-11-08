"""browser_interact: single actions, batches of steps, and the calls it refuses for a missing argument."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.tools import create_browser_tools


@pytest.mark.asyncio
async def test_browser_interact_click(mock_session: MagicMock) -> None:
    """Test browser_interact click action."""
    tools = create_browser_tools(mock_session)
    interact_tool = next(t for t in tools if t.name == "browser_interact_tool")

    result = await interact_tool.ainvoke({"action": "click", "ref": "e0"})

    assert "Clicked" in result
    mock_session.interact.assert_called_once_with("click", "e0", "", verify_goal=None)


@pytest.mark.asyncio
async def test_browser_interact_with_text(mock_session: MagicMock) -> None:
    """Test browser_interact with text parameter."""
    tools = create_browser_tools(mock_session)
    interact_tool = next(t for t in tools if t.name == "browser_interact_tool")

    await interact_tool.ainvoke({"action": "type", "ref": "e1", "text": "Hello"})

    mock_session.interact.assert_called_once_with("type", "e1", "Hello", verify_goal=None)


@pytest.mark.asyncio
async def test_browser_interact_batch_empty_steps(mock_session: MagicMock) -> None:
    tools = create_browser_tools(mock_session)
    interact_tool = next(t for t in tools if t.name == "browser_interact_tool")

    result = await interact_tool.ainvoke({"steps": []})

    assert "at least one action" in result


@pytest.mark.asyncio
async def test_browser_interact_requires_action_without_steps(mock_session: MagicMock) -> None:
    tools = create_browser_tools(mock_session)
    interact_tool = next(t for t in tools if t.name == "browser_interact_tool")

    result = await interact_tool.ainvoke({"action": "", "ref": "e0"})

    assert "action is required" in result


@pytest.mark.asyncio
async def test_browser_interact_requires_ref_without_steps(mock_session: MagicMock) -> None:
    tools = create_browser_tools(mock_session)
    interact_tool = next(t for t in tools if t.name == "browser_interact_tool")

    result = await interact_tool.ainvoke({"action": "click", "ref": ""})

    assert "ref is required" in result


@pytest.mark.asyncio
async def test_browser_interact_batch_steps(mock_session: MagicMock) -> None:
    """batch steps[] runs multiple interacts in one tool call."""
    mock_session.interact = AsyncMock(side_effect=["clicked", "filled"])

    tools = create_browser_tools(mock_session)
    interact_tool = next(t for t in tools if t.name == "browser_interact_tool")

    result = await interact_tool.ainvoke(
        {
            "steps": [
                {"action": "click", "ref": "e0"},
                {"action": "fill", "ref": "e1", "text": "hello"},
            ],
        }
    )

    assert "Step 1" in result
    assert "Step 2" in result
    assert mock_session.interact.await_count == 2
