"""Smoke tests for video_agent_tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from app.ai_agents.media_tools.video_agent_tool import create_video_generation_tool


@pytest.mark.asyncio
async def test_video_tool_list_action() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock(return_value='{"providers":[]}')
    engine.tool_description = "Video generation tool."
    tool = create_video_generation_tool(engine)

    result = await tool.ainvoke({"action": "list"})

    assert "providers" in result
    engine.execute.assert_awaited_once_with(
        "list",
        prompt=None,
        provider=None,
        model=None,
        duration_seconds=None,
        aspect_ratio=None,
        resolution=None,
        enable_audio=None,
        reference_images=None,
        reference_videos=None,
        force=False,
    )


def test_create_video_generation_tool_returns_basetool() -> None:
    engine = MagicMock()
    engine.tool_description = "desc"
    tool = create_video_generation_tool(engine)
    assert isinstance(tool, BaseTool)
    assert tool.name == "video_tool"
