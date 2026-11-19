"""Tests for video_tool: generate starts one task, list and status read, nothing degrades silently."""

from __future__ import annotations

import json
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig
from myrm_agent_harness.toolkits.llms.video.models import ProviderCapabilities
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus
from pydantic import ValidationError

from app.ai_agents.media_tools.video_agent_tool import create_video_generation_tool
from app.ai_agents.media_tools.video_schema import build_video_input_schema
from app.tasks.task_payload_crypto import seal_task_payload_secrets

_MODULE = "app.ai_agents.media_tools.video_agent_tool"


def _tool(
    *,
    provider: str = "volcengine",
    model: str = "seedance-2-0",
    allowed_roots: Sequence[str] = (),
    task_user_id: str = "default",
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> BaseTool:
    return create_video_generation_tool(
        VideoGenerationConfig(provider=provider, model=model),
        allowed_roots=allowed_roots,
        task_user_id=task_user_id,
        agent_id=agent_id,
        chat_id=chat_id,
    )


def _patched_enqueuer(task_id: str = "vid-1") -> tuple[MagicMock, MagicMock]:
    enqueuer = MagicMock()
    enqueuer.generate_video = AsyncMock(return_value=task_id)
    return MagicMock(return_value=enqueuer), enqueuer


def test_the_factory_returns_the_named_tool() -> None:
    tool = _tool()

    assert isinstance(tool, BaseTool)
    assert tool.name == "video_tool"
    for action in ("generate", "status", "list"):
        assert f"action='{action}'" in tool.description


def test_the_schema_has_no_force_flag_and_no_unknown_provider_names() -> None:
    tool = _tool()

    assert "force" not in tool.args
    assert "task_id" in tool.args
    assert "kling" not in tool.args["provider"]["description"]


@pytest.mark.asyncio
async def test_list_names_the_registered_providers() -> None:
    payload = json.loads(await _tool().ainvoke({"action": "list"}))

    assert {"gemini", "volcengine"} <= {provider["id"] for provider in payload["providers"]}


@pytest.mark.asyncio
async def test_generate_requires_a_prompt() -> None:
    enqueuer_cls, _ = _patched_enqueuer()

    with patch(f"{_MODULE}.AsyncVideoGenerationTools", enqueuer_cls):
        payload = json.loads(await _tool().ainvoke({"action": "generate", "prompt": "  "}))

    assert "prompt is required" in payload["error"]
    enqueuer_cls.assert_not_called()


@pytest.mark.asyncio
async def test_generate_starts_one_task_with_everything_it_was_given() -> None:
    enqueuer_cls, enqueuer = _patched_enqueuer("vid-7")
    store = MagicMock()
    tool = _tool(allowed_roots=["/work/chat-9"], task_user_id="user-1", agent_id="agent-42", chat_id="chat-99")

    with patch(f"{_MODULE}.AsyncVideoGenerationTools", enqueuer_cls), patch(f"{_MODULE}.media_task_store", return_value=store):
        payload = json.loads(
            await tool.ainvoke(
                {
                    "action": "generate",
                    "prompt": "a dog running",
                    "duration_seconds": 5,
                    "aspect_ratio": "16:9",
                    "resolution": "1080p",
                    "reference_images": ["media://media_ref"],
                    "reference_videos": [],
                    "negative_prompt": "blurry",
                    "seed": 7,
                }
            )
        )

    assert payload["tasks"] == [{"task_id": "vid-7", "task_type": "video_generate", "status": "pending"}]
    assert enqueuer_cls.call_args.args[1] is store
    assert enqueuer_cls.call_args.kwargs == {"payload_postprocessor": seal_task_payload_secrets}
    enqueuer.generate_video.assert_awaited_once_with(
        "a dog running",
        provider=None,
        model=None,
        duration_seconds=5,
        aspect_ratio="16:9",
        resolution="1080p",
        enable_audio=None,
        reference_images=["media://media_ref"],
        reference_videos=None,
        extra_params={"negative_prompt": "blurry", "seed": 7},
        allowed_roots=["/work/chat-9"],
        user_id="user-1",
        agent_id="agent-42",
        chat_id="chat-99",
    )


@pytest.mark.asyncio
async def test_generate_without_a_task_store_is_an_explicit_error() -> None:
    enqueuer_cls, _ = _patched_enqueuer()

    with (
        patch(f"{_MODULE}.AsyncVideoGenerationTools", enqueuer_cls),
        patch(f"{_MODULE}.media_task_store", side_effect=RuntimeError("task store not initialized")),
    ):
        payload = json.loads(await _tool().ainvoke({"action": "generate", "prompt": "a dog"}))

    assert payload == {"error": "Task store unavailable"}
    enqueuer_cls.assert_not_called()


@pytest.mark.asyncio
async def test_a_parameter_the_provider_lacks_is_passed_on_for_the_engine_to_report() -> None:
    """The pruned schema stays permissive (``extra=allow``); the generator reports what it ignored."""
    enqueuer_cls, enqueuer = _patched_enqueuer()
    tool = _tool(provider="minimax", model="MiniMax-Hailuo-2.3")

    assert "enable_audio" not in tool.args
    with patch(f"{_MODULE}.AsyncVideoGenerationTools", enqueuer_cls), patch(f"{_MODULE}.media_task_store"):
        payload = json.loads(await tool.ainvoke({"action": "generate", "prompt": "silent", "enable_audio": True}))

    assert "error" not in payload
    assert enqueuer.generate_video.await_args.kwargs["enable_audio"] is True


@pytest.mark.asyncio
async def test_an_unknown_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        await _tool().ainvoke({"action": "extend", "prompt": "a dog"})


@pytest.mark.asyncio
async def test_status_of_a_finished_video_returns_its_stored_references() -> None:
    result = {"video_urls": ["media://media_vid"], "provider": "volcengine", "model": "seedance-2-0", "count": 1}
    task = Task(task_id="vid-1", task_type="video_generate", user_id="u", status=TaskStatus.SUCCEEDED, payload={}, result=result)
    store = MagicMock()
    store.get_task = AsyncMock(return_value=task)

    with patch("app.ai_agents.media_tools.task_results.media_task_store", return_value=store):
        payload = json.loads(await _tool().ainvoke({"action": "status", "task_id": "vid-1"}))

    assert payload["status"] == "succeeded"
    assert payload["result"] == result


@pytest.mark.asyncio
async def test_status_reports_an_unknown_task_and_a_missing_id_explicitly() -> None:
    store = MagicMock()
    store.get_task = AsyncMock(return_value=None)

    with patch("app.ai_agents.media_tools.task_results.media_task_store", return_value=store):
        unknown = json.loads(await _tool().ainvoke({"action": "status", "task_id": "vid-missing"}))
        missing_id = json.loads(await _tool().ainvoke({"action": "status"}))

    assert unknown == {"error": "Task not found", "task_id": "vid-missing"}
    assert "task_id is required" in missing_id["error"]


@pytest.mark.parametrize(
    ("capabilities", "present", "absent"),
    [
        (
            ProviderCapabilities(supports_audio=False, supports_aspect_ratio=True, max_duration_seconds=5),
            {"aspect_ratio", "duration_seconds"},
            {"enable_audio", "reference_videos"},
        ),
        (
            ProviderCapabilities(supports_audio=True, supports_aspect_ratio=False, max_input_videos=2),
            {"enable_audio", "reference_videos"},
            {"aspect_ratio"},
        ),
    ],
)
def test_the_schema_drops_parameters_the_provider_cannot_use(
    capabilities: ProviderCapabilities, present: set[str], absent: set[str]
) -> None:
    properties = set(build_video_input_schema(capabilities).model_json_schema()["properties"])

    assert present <= properties
    assert not absent & properties


def test_the_schema_without_capabilities_keeps_every_parameter() -> None:
    properties = set(build_video_input_schema(None).model_json_schema()["properties"])

    assert {"enable_audio", "aspect_ratio", "reference_videos", "reference_images", "task_id"} <= properties
