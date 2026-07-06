"""Tests for image_agent_tool BaseTool wrapper and URL validation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from app.ai_agents.media_tools.image_agent_tool import (
    _validate_image_fetch_url,
    create_image_generation_tool,
)


def test_validate_image_fetch_url_allows_public_https() -> None:
    assert _validate_image_fetch_url("https://example.com/image.png") is None


def test_validate_image_fetch_url_blocks_private_ip() -> None:
    error = _validate_image_fetch_url("http://192.168.0.1/image.png")
    assert error is not None
    payload = json.loads(error)
    assert "error" in payload


def test_validate_image_fetch_url_allows_localhost_in_local_mode() -> None:
    assert _validate_image_fetch_url("http://localhost:8080/image.png", allow_private_networks=True) is None


@pytest.mark.asyncio
async def test_image_tool_list_action() -> None:
    engine = MagicMock()
    engine.list_models.return_value = '{"models":[]}'
    tool = create_image_generation_tool(engine)

    result = await tool.ainvoke({"action": "list"})

    assert result == '{"models":[]}'
    engine.list_models.assert_called_once()


@pytest.mark.asyncio
async def test_image_tool_generate_requires_prompt() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine)

    result = await tool.ainvoke({"action": "generate", "prompt": "  "})

    assert "prompt is required" in result
    engine.generate_image.assert_not_called()


@pytest.mark.asyncio
async def test_image_tool_edit_requires_prompt() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine)

    result = await tool.ainvoke(
        {
            "action": "edit",
            "prompt": "  ",
            "image_url": "https://example.com/source.png",
        }
    )

    payload = json.loads(result)
    assert "prompt is required" in payload["error"]


@pytest.mark.asyncio
async def test_image_tool_generate_delegates_to_engine_sync() -> None:
    engine = MagicMock()
    engine.generate_image = AsyncMock(return_value='{"image_url":"https://cdn.example/g.png"}')
    tool = create_image_generation_tool(engine)

    result = await tool.ainvoke({"action": "generate", "prompt": "a cat"})

    assert "image_url" in result
    engine.generate_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_tool_generate_enqueues_when_async_config() -> None:
    engine = MagicMock()
    engine.generate_image = AsyncMock()
    async_config = MagicMock()
    mock_store = MagicMock()

    with patch(
        "app.lifecycle.task_worker.get_task_store",
        return_value=mock_store,
    ), patch(
        "app.tasks.task_payload_crypto.seal_image_task_payload_after_enqueue",
        new_callable=AsyncMock,
    ), patch(
        "myrm_agent_harness.toolkits.llms.image.async_image_engine.AsyncImageGenerationTools",
    ) as async_cls:
        async_engine = MagicMock()
        async_engine.generate_image = AsyncMock(
            return_value='{"task_id":"img-abc","status":"pending"}',
        )
        async_cls.return_value = async_engine

        tool = create_image_generation_tool(
            engine,
            async_config=async_config,
            task_user_id="user-1",
            agent_id="agent-42",
            chat_id="chat-99",
        )
        result = await tool.ainvoke({"action": "generate", "prompt": "a cat"})

    payload = json.loads(result)
    assert payload["task_id"] == "img-abc"
    assert payload["status"] == "pending"
    engine.generate_image.assert_not_called()
    async_engine.generate_image.assert_awaited_once()
    call_kwargs = async_engine.generate_image.await_args.kwargs
    assert call_kwargs["user_id"] == "user-1"
    assert call_kwargs["agent_id"] == "agent-42"
    assert call_kwargs["chat_id"] == "chat-99"
    async_cls.assert_called_once_with(
        async_config,
        mock_store,
        ssrf_protection=True,
    )


@pytest.mark.asyncio
async def test_image_tool_generate_fallback_sync_when_task_store_unavailable() -> None:
    engine = MagicMock()
    engine.generate_image = AsyncMock(return_value='{"image_url":"https://cdn.example/g.png"}')
    async_config = MagicMock()

    with patch(
        "app.lifecycle.task_worker.get_task_store",
        side_effect=RuntimeError("task store not initialized"),
    ):
        tool = create_image_generation_tool(engine, async_config=async_config)
        result = await tool.ainvoke({"action": "generate", "prompt": "a cat"})

    assert "image_url" in result
    engine.generate_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_tool_edit_with_mask_fetches_both() -> None:
    engine = MagicMock()
    engine.edit_image = AsyncMock(return_value='{"image_url":"https://cdn.example/x.png"}')
    tool = create_image_generation_tool(engine, allow_private_networks=True)

    with patch(
        "app.ai_agents.media_tools.image_agent_tool._fetch_image_bytes",
        new=AsyncMock(side_effect=[(b"img", "image/png", 3), (b"mask", "image/png", 2)]),
    ) as fetch_mock:
        await tool.ainvoke(
            {
                "action": "edit",
                "prompt": "mask edit",
                "image_url": "http://localhost/source.png",
                "mask_url": "http://localhost/mask.png",
            }
        )

    assert fetch_mock.await_count == 2
    engine.edit_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_tool_edit_fetch_failure_returns_error() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine)

    with patch(
        "app.ai_agents.media_tools.image_agent_tool._fetch_image_bytes",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result = await tool.ainvoke(
            {
                "action": "edit",
                "prompt": "edit",
                "image_url": "https://example.com/source.png",
            }
        )

    payload = json.loads(result)
    assert "Failed to fetch image_url" in payload["error"]


@pytest.mark.asyncio
async def test_fetch_image_bytes_uses_httpx_in_local_mode() -> None:
    from app.ai_agents.media_tools.image_agent_tool import _fetch_image_bytes

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {"content-type": "image/jpeg"}
    response.content = b"jpeg"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.ai_agents.media_tools.image_agent_tool.httpx.AsyncClient",
        return_value=mock_client,
    ):
        body, mime, size = await _fetch_image_bytes(
            "http://localhost:8080/x.jpg",
            allow_private_networks=True,
        )

    assert body == b"jpeg"
    assert mime == "image/jpeg"
    assert size == 4
    mock_client.get.assert_awaited_once_with("http://localhost:8080/x.jpg")


@pytest.mark.asyncio
async def test_fetch_image_bytes_reads_response() -> None:
    from app.ai_agents.media_tools.image_agent_tool import _fetch_image_bytes

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {"content-type": "image/png"}
    response.content = b"abc"

    with patch(
        "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
        new_callable=AsyncMock,
        return_value=response,
    ):
        body, mime, size = await _fetch_image_bytes("https://example.com/x.png")

    assert body == b"abc"
    assert mime == "image/png"
    assert size == 3


@pytest.mark.asyncio
async def test_image_tool_edit_mask_fetch_failure_returns_error() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine)

    with patch(
        "app.ai_agents.media_tools.image_agent_tool._fetch_image_bytes",
        new=AsyncMock(side_effect=[(b"img", "image/png", 3), RuntimeError("mask fetch failed")]),
    ):
        result = await tool.ainvoke(
            {
                "action": "edit",
                "prompt": "edit",
                "image_url": "https://example.com/source.png",
                "mask_url": "https://example.com/mask.png",
            }
        )

    payload = json.loads(result)
    assert "Failed to fetch mask_url" in payload["error"]


@pytest.mark.asyncio
async def test_image_tool_edit_requires_image_url() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine)

    result = await tool.ainvoke({"action": "edit", "prompt": "make it blue"})

    payload = json.loads(result)
    assert "image_url is required" in payload["error"]


@pytest.mark.asyncio
async def test_image_tool_edit_blocks_ssrf_when_not_local_mode() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine, allow_private_networks=False)

    result = await tool.ainvoke(
        {
            "action": "edit",
            "prompt": "make it blue",
            "image_url": "http://127.0.0.1/image.png",
        }
    )

    payload = json.loads(result)
    assert "error" in payload
    engine.edit_image.assert_not_called()


@pytest.mark.asyncio
async def test_image_tool_edit_fetches_and_delegates_in_local_mode() -> None:
    engine = MagicMock()
    engine.edit_image = AsyncMock(return_value='{"image_url":"https://cdn.example/x.png"}')
    tool = create_image_generation_tool(engine, allow_private_networks=True)

    with patch(
        "app.ai_agents.media_tools.image_agent_tool._fetch_image_bytes",
        new=AsyncMock(return_value=(b"png-bytes", "image/png", 4)),
    ):
        result = await tool.ainvoke(
            {
                "action": "edit",
                "prompt": "make it blue",
                "image_url": "http://localhost:8080/source.png",
            }
        )

    assert "image_url" in result
    engine.edit_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_tool_edit_mask_url_ssrf_blocked() -> None:
    engine = MagicMock()
    tool = create_image_generation_tool(engine, allow_private_networks=False)

    with patch(
        "app.ai_agents.media_tools.image_agent_tool._fetch_image_bytes",
        new=AsyncMock(return_value=(b"img", "image/png", 3)),
    ):
        result = await tool.ainvoke(
            {
                "action": "edit",
                "prompt": "edit",
                "image_url": "https://example.com/source.png",
                "mask_url": "http://10.0.0.1/mask.png",
            }
        )

    payload = json.loads(result)
    assert "error" in payload
    engine.edit_image.assert_not_called()


def test_create_image_generation_tool_returns_basetool() -> None:
    engine = MagicMock()
    engine.tool_description = "desc"
    tool = create_image_generation_tool(engine)
    assert isinstance(tool, BaseTool)
    assert tool.name == "image_tool"
