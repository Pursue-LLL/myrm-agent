"""Unit tests for trigger_skill_evolution function.

Tests the gating logic and background task spawning.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.evolution.engine import trigger_skill_evolution


@pytest.mark.asyncio
async def test_trigger_skipped_when_no_tools_no_text() -> None:
    """Zero tool_steps and no conversation_text → no task created."""
    with patch("app.services.agent.evolution.engine.asyncio") as mock_asyncio:
        trigger_skill_evolution(
            chat_id="chat-1",
            model_cfg=MagicMock(),
            tool_steps_count=0,
            conversation_text=None,
        )
    mock_asyncio.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_fires_when_tools_used() -> None:
    """tool_steps_count > 0 → task created."""
    with patch("app.services.agent.evolution.engine.asyncio") as mock_asyncio:
        trigger_skill_evolution(
            chat_id="chat-2",
            model_cfg=MagicMock(),
            tool_steps_count=3,
        )
    mock_asyncio.create_task.assert_called_once()
    call_kwargs = mock_asyncio.create_task.call_args
    assert "skill_evolution_chat-2" in str(call_kwargs)


@pytest.mark.asyncio
async def test_trigger_fires_when_conversation_text_provided() -> None:
    """conversation_text provided (DW) → task created even with 0 tools."""
    with patch("app.services.agent.evolution.engine.asyncio") as mock_asyncio:
        trigger_skill_evolution(
            chat_id="chat-dw",
            model_cfg=MagicMock(),
            tool_steps_count=0,
            conversation_text="DW result content here",
        )
    mock_asyncio.create_task.assert_called_once()
