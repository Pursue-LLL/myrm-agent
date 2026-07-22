"""Smoke tests for video_agent_tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.ai_agents.media_tools.video_agent_tool import create_video_generation_tool
from app.tasks.task_payload_crypto import seal_task_payload_secrets


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


@pytest.mark.asyncio
async def test_video_tool_generate_action() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock(return_value='{"task_id":"t1"}')
    engine.tool_description = "Video generation tool."
    tool = create_video_generation_tool(engine)

    result = await tool.ainvoke({"action": "generate", "prompt": "a sunset"})

    assert "task_id" in result
    engine.execute.assert_awaited_once_with(
        "generate",
        prompt="a sunset",
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


@pytest.mark.asyncio
async def test_video_tool_generate_requires_prompt() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock()
    engine.tool_description = "Video generation tool."
    tool = create_video_generation_tool(engine)

    result = await tool.ainvoke({"action": "generate", "prompt": "  "})

    assert "prompt is required" in result
    engine.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_video_tool_status_action() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock(return_value='{"status":"completed"}')
    engine.tool_description = "Video generation tool."
    tool = create_video_generation_tool(engine)

    result = await tool.ainvoke({"action": "status"})

    assert "completed" in result
    engine.execute.assert_awaited_once_with(
        "status",
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


@pytest.mark.asyncio
async def test_video_tool_generate_enqueues_when_async_config() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock()
    engine.tool_description = "Video generation tool."
    async_config = MagicMock()
    mock_store = MagicMock()

    with patch(
        "app.lifecycle.task_worker.get_task_store",
        return_value=mock_store,
    ), patch(
        "app.ai_agents.media_tools.video_agent_tool.AsyncVideoGenerationTools",
    ) as async_cls:
        async_engine = MagicMock()
        async_engine.generate_video = AsyncMock(
            return_value='{"task_id":"vid-abc","task_type":"video_generate","status":"pending"}'
        )
        async_cls.return_value = async_engine

        tool = create_video_generation_tool(
            engine,
            async_config=async_config,
            task_user_id="user-1",
            agent_id="agent-42",
            chat_id="chat-99",
        )
        result = await tool.ainvoke({"action": "generate", "prompt": "sunset clip"})

    payload = json.loads(result)
    assert payload["task_id"] == "vid-abc"
    assert payload["task_type"] == "video_generate"
    engine.execute.assert_not_awaited()
    async_engine.generate_video.assert_awaited_once()
    call_kwargs = async_engine.generate_video.await_args.kwargs
    assert call_kwargs["user_id"] == "user-1"
    assert call_kwargs["agent_id"] == "agent-42"
    assert call_kwargs["chat_id"] == "chat-99"
    async_cls.assert_called_once_with(
        async_config,
        mock_store,
        payload_postprocessor=seal_task_payload_secrets,
    )


@pytest.mark.asyncio
async def test_video_tool_status_with_task_id_reads_task_store() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock(return_value='{"status":"idle"}')
    engine.tool_description = "Video generation tool."
    task = Task(
        task_id="vid-1",
        task_type="video_generate",
        user_id="user-1",
        status=TaskStatus.RUNNING,
        payload={"prompt": "sunset clip"},
        progress=0.5,
    )
    mock_store = MagicMock()
    mock_store.get_task = AsyncMock(return_value=task)

    with patch(
        "app.lifecycle.task_worker.get_task_store",
        return_value=mock_store,
    ):
        tool = create_video_generation_tool(engine)
        result = await tool.ainvoke({"action": "status", "task_id": "vid-1"})

    payload = json.loads(result)
    assert payload["task_id"] == "vid-1"
    assert payload["status"] == "running"
    assert payload["task_type"] == "video_generate"
    mock_store.get_task.assert_awaited_once_with("vid-1")
    engine.execute.assert_not_awaited()
