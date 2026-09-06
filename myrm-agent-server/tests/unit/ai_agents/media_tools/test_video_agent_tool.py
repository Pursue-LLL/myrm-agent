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

    with (
        patch(
            "app.lifecycle.task_worker.get_task_store",
            return_value=mock_store,
        ),
        patch(
            "app.ai_agents.media_tools.video_agent_tool.AsyncVideoGenerationTools",
        ) as async_cls,
    ):
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
async def test_video_tool_async_config_description_contains_workflow() -> None:
    engine = MagicMock()
    engine.tool_description = "Video generation tool. Active: luma/ray-2."
    async_config = MagicMock()
    tool = create_video_generation_tool(engine, async_config=async_config)
    assert "Workflow:" in tool.description
    assert "action='generate'" in tool.description
    assert "action='status'" in tool.description
    assert "luma/ray-2" in tool.description


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


@pytest.mark.asyncio
async def test_video_tool_generate_passes_negative_prompt_and_seed() -> None:
    engine = MagicMock()
    engine.execute = AsyncMock(return_value='{"task_id":"t2"}')
    engine.tool_description = "Video generation tool."
    tool = create_video_generation_tool(engine)

    result = await tool.ainvoke(
        {
            "action": "generate",
            "prompt": "a sunset",
            "negative_prompt": "blurry, distorted",
            "seed": 42,
        }
    )

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
        extra_params={"negative_prompt": "blurry, distorted", "seed": 42},
        force=False,
    )


@pytest.mark.asyncio
async def test_video_tool_dynamic_schema_diet_omits_unsupported_audio() -> None:
    """Verify that when a provider does not support audio, enable_audio is omitted from tool args."""
    from myrm_agent_harness.toolkits.llms.video.models import ProviderCapabilities

    mock_provider = MagicMock()
    mock_provider.capabilities = ProviderCapabilities(
        supports_audio=False,
        supports_aspect_ratio=True,
        max_duration_seconds=5,
    )
    engine = MagicMock()
    engine._config.provider = "kling-no-audio"
    engine._registry.get.return_value = mock_provider
    engine.tool_description = "Video generation tool."

    tool = create_video_generation_tool(engine)
    schema_props = tool.args_schema.model_json_schema()["properties"]

    assert "enable_audio" not in schema_props
    assert "aspect_ratio" in schema_props
    assert "duration_seconds" in schema_props


@pytest.mark.asyncio
async def test_video_tool_moderation_blocked_error_returns_terminal_json() -> None:
    """Verify that ModerationBlockedError is caught and converted to non-retryable terminal JSON."""
    from myrm_agent_harness.toolkits.llms.video import ModerationBlockedError

    engine = MagicMock()
    engine.execute = AsyncMock(
        side_effect=ModerationBlockedError(
            "Rejected by safety policy",
            violation_reason="Content flagged for NSFW safety policy violation",
        )
    )
    engine.tool_description = "Video generation tool."

    tool = create_video_generation_tool(engine)
    result = await tool.ainvoke({"action": "generate", "prompt": "unsafe content"})

    payload = json.loads(result)
    assert payload["code"] == "MODERATION_BLOCKED"
    assert payload["retryable"] is False
    assert "NSFW" in payload["reason"]
    assert "adjust the wording" in payload["tip"]


@pytest.mark.asyncio
async def test_video_tool_unsupported_audio_sanitized_gracefully() -> None:
    """Verify that if caller passes enable_audio=True for a provider without audio, it is sanitized to False without ValidationError."""
    from myrm_agent_harness.toolkits.llms.video.models import ProviderCapabilities

    mock_provider = MagicMock()
    mock_provider.capabilities = ProviderCapabilities(
        supports_audio=False,
        supports_aspect_ratio=True,
    )
    engine = MagicMock()
    engine._config.provider = "kling-no-audio"
    engine._registry.get.return_value = mock_provider
    engine.execute = AsyncMock(return_value='{"task_id":"t-audio"}')
    engine.tool_description = "Video generation tool."

    tool = create_video_generation_tool(engine)
    # The schema doesn't advertise enable_audio, but extra="allow" permits it without crashing,
    # and _enqueue_generate sanitizes enable_audio to False
    result = await tool.ainvoke({"action": "generate", "prompt": "a silent scene", "enable_audio": True})
    assert "t-audio" in result
    call_kwargs = engine.execute.await_args.kwargs
    assert call_kwargs["enable_audio"] is False


