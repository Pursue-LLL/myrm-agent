"""Tests for image_tool: generate fans out one task per image, edit answers in the call, nothing degrades silently."""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus
from PIL import Image
from pydantic import ValidationError

from app.ai_agents.media_tools.image_agent_tool import create_image_generation_tool
from app.tasks.task_payload_crypto import seal_task_payload_secrets

_MODULE = "app.ai_agents.media_tools.image_agent_tool"
_MODEL = "gpt-image-2.6-sunburst"


def _png(size: tuple[int, int] = (8, 8)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _tool(
    *,
    allowed_roots: Sequence[str] = (),
    task_user_id: str = "default",
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> BaseTool:
    return create_image_generation_tool(
        ImageGenerationConfig(model=_MODEL),
        allowed_roots=allowed_roots,
        task_user_id=task_user_id,
        agent_id=agent_id,
        chat_id=chat_id,
    )


def _patched_enqueuer(task_ids: list[str]) -> tuple[MagicMock, MagicMock]:
    enqueuer = MagicMock()
    enqueuer.generate_image = AsyncMock(side_effect=task_ids)
    return MagicMock(return_value=enqueuer), enqueuer


def _patched_editor(response: str = '{"images":[{"url":"media://media_edit","mime_type":"image/png"}]}') -> MagicMock:
    editor = MagicMock()
    editor.edit_image = AsyncMock(return_value=response)
    return editor


def test_the_factory_returns_the_named_tool() -> None:
    tool = _tool()

    assert isinstance(tool, BaseTool)
    assert tool.name == "image_tool"
    for action in ("generate", "edit", "status", "list"):
        assert f"action='{action}'" in tool.description


def test_the_schema_carries_official_parameters_only() -> None:
    tool = _tool()

    assert set(tool.args) == {
        "action",
        "prompt",
        "size",
        "quality",
        "n",
        "reference_image_urls",
        "image_url",
        "mask_url",
        "task_id",
    }
    assert "style" not in tool.args
    assert tool.args["quality"]["anyOf"][0]["enum"] == ["low", "medium", "high"]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_input", [{"quality": "hd"}, {"n": 0}, {"n": 5}, {"action": "regenerate"}])
async def test_values_outside_the_schema_are_rejected_before_any_work(bad_input: dict[str, object]) -> None:
    enqueuer_cls, _ = _patched_enqueuer([])

    with patch(f"{_MODULE}.AsyncImageGenerationTools", enqueuer_cls), pytest.raises(ValidationError):
        await _tool().ainvoke({"action": "generate", "prompt": "a cat", **bad_input})

    enqueuer_cls.assert_not_called()


@pytest.mark.asyncio
async def test_list_returns_the_catalog_with_the_selected_model() -> None:
    payload = json.loads(await _tool().ainvoke({"action": "list"}))

    assert payload["active_model"] == _MODEL
    assert len(payload["models"]) > 1


@pytest.mark.asyncio
async def test_generate_requires_a_prompt() -> None:
    enqueuer_cls, _ = _patched_enqueuer([])

    with patch(f"{_MODULE}.AsyncImageGenerationTools", enqueuer_cls):
        payload = json.loads(await _tool().ainvoke({"action": "generate", "prompt": "  "}))

    assert "prompt is required" in payload["error"]
    enqueuer_cls.assert_not_called()


@pytest.mark.asyncio
async def test_generate_starts_one_task_per_image() -> None:
    enqueuer_cls, enqueuer = _patched_enqueuer(["img-1", "img-2", "img-3"])
    store = MagicMock()
    tool = _tool(allowed_roots=["/work/chat-9"], task_user_id="user-1", agent_id="agent-42", chat_id="chat-99")

    with patch(f"{_MODULE}.AsyncImageGenerationTools", enqueuer_cls), patch(f"{_MODULE}.media_task_store", return_value=store):
        payload = json.loads(
            await tool.ainvoke(
                {
                    "action": "generate",
                    "prompt": "a cat",
                    "size": "1536x1024",
                    "quality": "high",
                    "n": 3,
                    "reference_image_urls": [" media://media_ref ", "  "],
                }
            )
        )

    assert [task["task_id"] for task in payload["tasks"]] == ["img-1", "img-2", "img-3"]
    assert {(task["task_type"], task["status"]) for task in payload["tasks"]} == {("image_generate", "pending")}
    enqueuer_cls.assert_called_once()
    assert enqueuer_cls.call_args.args[1] is store
    assert enqueuer_cls.call_args.kwargs == {"payload_postprocessor": seal_task_payload_secrets}
    assert enqueuer.generate_image.await_count == 3
    for call in enqueuer.generate_image.await_args_list:
        assert call.args == ("a cat",)
        assert call.kwargs == {
            "size": "1536x1024",
            "quality": "high",
            "reference_image_urls": ["media://media_ref"],
            "allowed_roots": ["/work/chat-9"],
            "user_id": "user-1",
            "agent_id": "agent-42",
            "chat_id": "chat-99",
        }


@pytest.mark.asyncio
async def test_generate_without_a_task_store_is_an_explicit_error_not_a_sync_fallback() -> None:
    enqueuer_cls, _ = _patched_enqueuer([])
    editor = _patched_editor()

    with (
        patch(f"{_MODULE}.ImageGenerationTools", return_value=editor),
        patch(f"{_MODULE}.AsyncImageGenerationTools", enqueuer_cls),
        patch(f"{_MODULE}.media_task_store", side_effect=RuntimeError("task store not initialized")),
    ):
        payload = json.loads(await _tool().ainvoke({"action": "generate", "prompt": "a cat"}))

    assert payload == {"error": "Task store unavailable"}
    enqueuer_cls.assert_not_called()
    editor.edit_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_resolves_image_and_mask_through_the_single_resolver() -> None:
    image, mask = _png(), _png((4, 4))
    editor = _patched_editor()
    resolve = AsyncMock(side_effect=[[image], [mask]])

    with patch(f"{_MODULE}.ImageGenerationTools", return_value=editor), patch(f"{_MODULE}.resolve_media_inputs", resolve):
        tool = _tool(allowed_roots=["/work/chat-9"])
        payload = json.loads(
            await tool.ainvoke(
                {
                    "action": "edit",
                    "prompt": "make it blue",
                    "image_url": "media://media_src",
                    "mask_url": "mask.png",
                    "size": "1024x1024",
                }
            )
        )

    assert payload["images"][0]["url"] == "media://media_edit"
    image_call, mask_call = resolve.await_args_list
    assert image_call.args[:2] == (["media://media_src"], "image")
    assert image_call.kwargs == {"field_name": "image_url"}
    assert mask_call.args[:2] == (["mask.png"], "image")
    assert mask_call.kwargs == {"field_name": "mask_url"}
    # A mask means something by its transparency, so only the image goes through the downsizing hook.
    assert image_call.args[2].image_hook is not None
    assert mask_call.args[2].image_hook is None
    assert [str(root) for root in image_call.args[2].allowed_roots] == ["/work/chat-9"]
    editor.edit_image.assert_awaited_once_with(
        image,
        "make it blue",
        mask=mask,
        size="1024x1024",
        quality=None,
        image_mime="image/png",
        image_size_bytes=len(image),
    )


@pytest.mark.asyncio
async def test_edit_passes_the_quality_it_was_given_to_the_engine() -> None:
    editor = _patched_editor()

    with (
        patch(f"{_MODULE}.ImageGenerationTools", return_value=editor),
        patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(return_value=_png())),
    ):
        arguments = {"action": "edit", "prompt": "brighter", "image_url": "media://media_src", "quality": "high"}
        await _tool().ainvoke(arguments)

    assert editor.edit_image.await_args.kwargs["quality"] == "high"


@pytest.mark.asyncio
async def test_edit_reads_a_media_library_image_end_to_end() -> None:
    editor = _patched_editor()
    source = _png((32, 32))

    with (
        patch(f"{_MODULE}.ImageGenerationTools", return_value=editor),
        patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(return_value=source)) as read,
    ):
        payload = json.loads(await _tool().ainvoke({"action": "edit", "prompt": "brighter", "image_url": "media://media_src"}))

    read.assert_awaited_once_with("media_src")
    assert "error" not in payload
    sent = editor.edit_image.await_args.args[0]
    with Image.open(io.BytesIO(sent)) as decoded:
        assert decoded.size == (32, 32)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"prompt": "make it blue"}, "image_url is required"),
        ({"prompt": "  ", "image_url": "media://media_src"}, "prompt is required"),
        ({"prompt": "make it blue", "image_url": "media://media_src", "n": 2}, "one image per call"),
    ],
)
async def test_edit_rejects_incomplete_requests_without_calling_the_engine(arguments: dict[str, object], expected: str) -> None:
    editor = _patched_editor()

    with patch(f"{_MODULE}.ImageGenerationTools", return_value=editor):
        payload = json.loads(await _tool().ainvoke({"action": "edit", **arguments}))

    assert expected in payload["error"]
    editor.edit_image.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "field"),
    [
        ({"image_url": "file:///etc/passwd"}, "image_url"),
        ({"image_url": "media://media_src", "mask_url": "file:///etc/passwd"}, "mask_url"),
    ],
)
async def test_edit_names_the_reference_it_cannot_use(arguments: dict[str, object], field: str) -> None:
    editor = _patched_editor()

    with (
        patch(f"{_MODULE}.ImageGenerationTools", return_value=editor),
        patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(return_value=_png())),
    ):
        payload = json.loads(await _tool().ainvoke({"action": "edit", "prompt": "brighter", **arguments}))

    assert payload["error"].startswith(f"{field}: ")
    editor.edit_image.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "parameter", "owner"),
    [
        ({"action": "generate", "prompt": "a cat", "image_url": "media://media_src"}, "image_url", "edit"),
        ({"action": "generate", "prompt": "a cat", "mask_url": "mask.png"}, "mask_url", "edit"),
        ({"action": "generate", "prompt": "a cat", "task_id": "img-1"}, "task_id", "status"),
        (
            {
                "action": "edit",
                "prompt": "brighter",
                "image_url": "media://media_src",
                "reference_image_urls": ["media://media_ref"],
            },
            "reference_image_urls",
            "generate",
        ),
        (
            {"action": "edit", "prompt": "brighter", "image_url": "media://media_src", "task_id": "img-1"},
            "task_id",
            "status",
        ),
    ],
)
async def test_a_parameter_of_another_action_is_refused_instead_of_dropped(
    arguments: dict[str, object], parameter: str, owner: str
) -> None:
    enqueuer_cls, _ = _patched_enqueuer([])
    editor = _patched_editor()

    with (
        patch(f"{_MODULE}.ImageGenerationTools", return_value=editor),
        patch(f"{_MODULE}.AsyncImageGenerationTools", enqueuer_cls),
    ):
        payload = json.loads(await _tool().ainvoke(arguments))

    assert f"{parameter} is a parameter of action={owner}, not of action={arguments['action']}" in payload["error"]
    enqueuer_cls.assert_not_called()
    editor.edit_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_blank_parameters_of_another_action_count_as_left_out() -> None:
    enqueuer_cls, _ = _patched_enqueuer(["img-1"])
    editor = _patched_editor()
    blanks: dict[str, object] = {"image_url": "  ", "mask_url": "", "task_id": " "}

    with (
        patch(f"{_MODULE}.ImageGenerationTools", return_value=editor),
        patch(f"{_MODULE}.AsyncImageGenerationTools", enqueuer_cls),
        patch(f"{_MODULE}.media_task_store", return_value=MagicMock()),
        patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(return_value=_png())),
    ):
        started = json.loads(await _tool().ainvoke({"action": "generate", "prompt": "a cat", **blanks}))
        edited = json.loads(
            await _tool().ainvoke(
                {
                    "action": "edit",
                    "prompt": "brighter",
                    "image_url": "media://media_src",
                    "reference_image_urls": [" ", ""],
                    "task_id": "",
                }
            )
        )

    assert [task["task_id"] for task in started["tasks"]] == ["img-1"]
    assert edited["images"][0]["url"] == "media://media_edit"


@pytest.mark.asyncio
async def test_status_requires_a_task_id() -> None:
    payload = json.loads(await _tool().ainvoke({"action": "status"}))

    assert "task_id is required" in payload["error"]


@pytest.mark.asyncio
async def test_status_reports_an_unknown_task_explicitly() -> None:
    store = MagicMock()
    store.get_task = AsyncMock(return_value=None)

    with patch("app.ai_agents.media_tools.task_results.media_task_store", return_value=store):
        payload = json.loads(await _tool().ainvoke({"action": "status", "task_id": "img-missing"}))

    assert payload == {"error": "Task not found", "task_id": "img-missing"}


@pytest.mark.asyncio
async def test_status_reports_an_unavailable_store_explicitly() -> None:
    with patch("app.ai_agents.media_tools.task_results.media_task_store", side_effect=RuntimeError("not started")):
        payload = json.loads(await _tool().ainvoke({"action": "status", "task_id": "img-1"}))

    assert payload == {"error": "Task store unavailable", "task_id": "img-1"}


@pytest.mark.asyncio
async def test_status_of_a_finished_task_returns_its_stored_result() -> None:
    result = {"images": [{"url": "media://media_done", "mime_type": "image/png"}], "model": _MODEL}
    task = Task(task_id="img-1", task_type="image_generate", user_id="u", status=TaskStatus.SUCCEEDED, payload={}, result=result)
    store = MagicMock()
    store.get_task = AsyncMock(return_value=task)

    with patch("app.ai_agents.media_tools.task_results.media_task_store", return_value=store):
        payload = json.loads(await _tool().ainvoke({"action": "status", "task_id": "img-1"}))

    assert payload["status"] == "succeeded"
    assert payload["result"] == result
    assert "next_step" not in payload


@pytest.mark.asyncio
async def test_status_of_a_failed_task_tells_the_model_what_to_do_next() -> None:
    task = Task(task_id="img-2", task_type="image_generate", user_id="u", status=TaskStatus.FAILED, payload={})
    store = MagicMock()
    store.get_task = AsyncMock(return_value=task)

    with patch("app.ai_agents.media_tools.task_results.media_task_store", return_value=store):
        payload = json.loads(await _tool().ainvoke({"action": "status", "task_id": "img-2"}))

    assert payload["status"] == "failed"
    assert "do not reword the prompt" in payload["next_step"]
