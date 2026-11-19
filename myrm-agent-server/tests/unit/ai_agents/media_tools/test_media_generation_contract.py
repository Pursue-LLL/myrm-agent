"""Contract: what the media tools return, and what the chat registers from it, is exactly what the client expects.

[INPUT]
- shared/config/media_generation_contract.json (POS: the result shapes and registration cases both sides are held to)
- app.ai_agents.media_tools.task_results::started_tasks_result (POS: the generate answer of image_tool and video_tool)
- app.ai_agents.media_tools.tts_agent_tool::TTSTool (POS: the speech answer)
- app.tasks.executors.image_executor::ImageTaskExecutor, app.tasks.executors.video_executor::VideoTaskExecutor (POS: the results of finished tasks)
- app.services.agent.streaming_support.media_generated::collect_media_generated (POS: registers the cards of a message)
- myrm_agent_harness.toolkits.llms.image (POS: the edit answer and the model catalog)

[OUTPUT]
Fails when a producer drops or renames a field a card reads, stores a non-``media://`` address, registers a different
entry than the shared cases say, or when the catalog and the client's model list drift apart.

[POS]
tests/unit/ai_agents/media_tools/test_media_generation_contract.py; the client half is
myrm-agent-frontend/src/lib/chat/__tests__/mediaGenerationContract.test.ts, which reads the same file.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.image import ImageGenerator
from myrm_agent_harness.toolkits.llms.image.image_engine import ImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig, ImageResult
from myrm_agent_harness.toolkits.llms.image.types import BUILTIN_PROFILES
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_IMAGE_GENERATE, TASK_TYPE_VIDEO_GENERATE
from myrm_agent_harness.toolkits.llms.tts import TTSConfig, TTSResult
from myrm_agent_harness.toolkits.llms.video.models import VideoResult
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.ai_agents.media_tools.task_results import started_tasks_result
from app.ai_agents.media_tools.tts_agent_tool import TTSTool
from app.services.agent.streaming_support.media_generated import collect_media_generated
from app.tasks.executors.image_executor import ImageTaskExecutor
from app.tasks.executors.video_executor import VideoTaskExecutor

_CONTRACT = json.loads(
    (Path(__file__).resolve().parents[5] / "shared" / "config" / "media_generation_contract.json").read_text(encoding="utf-8")
)
_SHAPES: Mapping[str, Mapping[str, Mapping[str, object]]] = _CONTRACT["shapes"]
_EXAMPLES: Mapping[str, dict[str, object]] = _CONTRACT["examples"]
_CASES: list[dict[str, object]] = _CONTRACT["collector_cases"]
_MEDIA_PREFIX = "media://"
_EDIT_MODEL = "gpt-image-2.6-sunburst"


def _violations(spec: object, value: object, path: str = "$") -> list[str]:
    """What is wrong with ``value`` against a shape name or a field spec; empty when it conforms."""
    if isinstance(spec, str) and spec in _SHAPES:
        return _shape_violations(_SHAPES[spec], value, path)
    if spec == "string":
        return [] if isinstance(value, str) and value else [f"{path}: expected a non-empty string"]
    if spec == "number":
        return [] if isinstance(value, (int, float)) and not isinstance(value, bool) else [f"{path}: expected a number"]
    if spec == "media_reference":
        ok = isinstance(value, str) and value.startswith(_MEDIA_PREFIX) and len(value) > len(_MEDIA_PREFIX)
        return [] if ok else [f"{path}: expected a media:// reference"]
    if isinstance(spec, dict) and "one_of" in spec:
        return [] if value in spec["one_of"] else [f"{path}: expected one of {spec['one_of']}"]
    if isinstance(spec, dict) and "list" in spec:
        if not isinstance(value, list) or not value:
            return [f"{path}: expected a non-empty list"]
        return [error for i, item in enumerate(value) for error in _violations(spec["list"], item, f"{path}[{i}]")]
    raise AssertionError(f"unknown field spec {spec!r} at {path}")


def _shape_violations(shape: Mapping[str, Mapping[str, object]], value: object, path: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{path}: expected an object"]
    errors: list[str] = []
    for name, spec in shape.get("required", {}).items():
        if name not in value:
            errors.append(f"{path}.{name}: missing")
        else:
            errors.extend(_violations(spec, value[name], f"{path}.{name}"))
    for name, spec in shape.get("optional", {}).items():
        if name in value:
            errors.extend(_violations(spec, value[name], f"{path}.{name}"))
    return errors


def _assert_conforms(shape: str, value: object) -> None:
    assert _violations(shape, value) == []


def test_every_example_conforms_to_its_shape() -> None:
    assert set(_EXAMPLES) <= set(_SHAPES)
    for name, example in _EXAMPLES.items():
        _assert_conforms(name, example)


@pytest.mark.parametrize(
    ("shape", "broken"),
    [
        ("image_result", lambda v: {k: x for k, x in v.items() if k != "images"}),
        ("image_result", lambda v: {**v, "images": [{"url": "https://cdn.example/a.png", "mime_type": "image/png"}]}),
        ("image_result", lambda v: {**v, "images": []}),
        ("image_result", lambda v: {k: x for k, x in v.items() if k != "model"}),
        ("image_result", lambda v: {**v, "latency_ms": "8200"}),
        ("video_result", lambda v: {k: x for k, x in v.items() if k != "video_urls"}),
        ("video_result", lambda v: {**v, "video_urls": ["https://cdn.example/a.mp4"]}),
        ("speech_result", lambda v: {k: x for k, x in v.items() if k != "audio_url"}),
        ("speech_result", lambda v: {**v, "audio_url": "file:///tmp/a.mp3"}),
        ("generate_result", lambda v: {"task_ids": [t["task_id"] for t in v["tasks"]]}),
        ("generate_result", lambda v: {"tasks": [{**v["tasks"][0], "task_id": ""}]}),
        ("stored_entry", lambda v: {**v, "kind": "video"}),
        ("task_entry", lambda v: {**v, "kind": "tts"}),
    ],
)
def test_the_checks_catch_a_renamed_or_unstored_field(shape: str, broken: Callable[[dict[str, object]], object]) -> None:
    assert _violations(shape, broken(_EXAMPLES[shape])) != []


def test_the_clients_image_models_are_the_engine_catalog() -> None:
    assert _CONTRACT["image_models"] == list(BUILTIN_PROFILES)


def test_a_generate_call_answers_with_the_started_tasks_of_either_tool() -> None:
    for task_type in (TASK_TYPE_IMAGE_GENERATE, TASK_TYPE_VIDEO_GENERATE):
        answer = json.loads(started_tasks_result(task_type, ["task_a", "task_b"], message="started"))

        _assert_conforms("generate_result", answer)
        assert [task["task_type"] for task in answer["tasks"]] == [task_type, task_type]


def _task(task_type: str, **payload: object) -> Task:
    return Task(
        task_id="contract-task",
        task_type=task_type,
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "a red fox in the snow", **payload},
    )


@pytest.mark.asyncio
async def test_a_finished_image_task_holds_the_image_result() -> None:
    generated = ImageResult(
        url="https://cdn.example/temporary.png",
        b64_json=None,
        revised_prompt=None,
        model=_EDIT_MODEL,
        latency_ms=8200.4,
        persisted_ref="media://media_img_1",
        mime_type="image/png",
    )
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=generated)

    with patch("app.tasks.executors.image_executor.ImageGenerator", MagicMock(return_value=generator)):
        result = await ImageTaskExecutor(MagicMock()).execute(_task(TASK_TYPE_IMAGE_GENERATE))

    _assert_conforms("image_result", result)


@pytest.mark.asyncio
async def test_a_finished_video_task_holds_the_video_result() -> None:
    generated = VideoResult(
        videos=[],
        provider="gemini",
        model="veo-3.1-fast-generate-preview",
        latency_ms=61000.0,
        persisted_refs=["media://media_vid_1"],
    )
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=generated)

    with patch("app.tasks.executors.video_executor.VideoGenerator", MagicMock(return_value=generator)):
        result = await VideoTaskExecutor(MagicMock()).execute(_task(TASK_TYPE_VIDEO_GENERATE))

    _assert_conforms("video_result", result)


@pytest.mark.asyncio
async def test_a_synchronous_image_edit_answers_with_the_image_result() -> None:
    edited = ImageResult(
        url=None,
        b64_json=None,
        revised_prompt=None,
        model=_EDIT_MODEL,
        latency_ms=7400.0,
        persisted_ref="media://media_edit_1",
        mime_type="image/png",
    )
    editor = ImageGenerationTools(ImageGenerationConfig(model=_EDIT_MODEL))

    with patch.object(ImageGenerator, "edit", AsyncMock(return_value=edited)):
        answer = json.loads(await editor.edit_image(b"png", "add a red scarf", image_mime="image/png", image_size_bytes=3))

    _assert_conforms("image_result", answer)


@pytest.mark.asyncio
async def test_a_speech_call_answers_with_the_speech_result() -> None:
    spoken = TTSResult(
        audio_bytes=b"audio",
        mime_type="audio/mpeg",
        provider="openai",
        model="gpt-4o-mini-tts",
        latency_ms=150.0,
        persisted_ref="media://media_speech",
        duration_seconds=3.24,
    )
    config = TTSConfig(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key="test-key")

    with patch("app.ai_agents.media_tools.tts_agent_tool.AsyncTTSEngine.generate", AsyncMock(return_value=spoken)):
        answer = json.loads(await TTSTool(config).ainvoke({"text": "Hello"}))

    _assert_conforms("speech_result", answer)


@pytest.mark.parametrize("as_json_text", [True, False], ids=["result as JSON text", "result as an object"])
@pytest.mark.parametrize("case", _CASES, ids=[str(case["name"]) for case in _CASES])
def test_the_chat_registers_what_the_shared_cases_say(case: dict[str, object], as_json_text: bool) -> None:
    result = json.dumps(case["result"]) if as_json_text else case["result"]
    entries: list[dict[str, object]] = []

    collect_media_generated(entries, {"tool_name": case["tool"], "result": result})

    assert entries == case["entries"]
    for entry in entries:
        _assert_conforms("task_entry" if "task_id" in entry else "stored_entry", entry)
