"""The media a media tool call produced, registered from the tool's structured result.

[INPUT]
- app.core.media.reference::parse_media_reference (POS: ``media://<id>`` artifact identity)
- app.services.agent.streaming_support.stream_collector_helpers::parse_tool_end_result (POS: tool result JSON decode)

[OUTPUT]
- collect_media_generated(): append the entries a ``tool_end`` event registers to a message's ``media_generated``

[POS]
A message shows a card for every image, video and audio its tools produced, and that never depends on what the
model writes about them: the entries come from the result the tool returned, so they survive a reply that says
nothing, is cut off or is not even JSON. Asynchronous generations register the task (the card follows its progress);
synchronous ones (an image edit, speech) register the stored media. ``status`` and ``list`` results register nothing.
The client parses the same results into the same entries (``recordMediaGenerated``); both are held to
``shared/config/media_generation_contract.json``.
"""

from __future__ import annotations

from app.core.media.reference import parse_media_reference
from app.services.agent.streaming_support.stream_collector_helpers import parse_tool_end_result

_IMAGE_TOOL = "image_tool"
_VIDEO_TOOL = "video_tool"
_TTS_TOOL = "tts_generate"


def _task_entries(kind: str, result: dict[str, object]) -> list[dict[str, object]]:
    tasks = result.get("tasks")
    if not isinstance(tasks, list):
        return []
    entries: list[dict[str, object]] = []
    for task in tasks:
        task_id = task.get("task_id") if isinstance(task, dict) else None
        if isinstance(task_id, str) and task_id:
            entries.append({"kind": kind, "task_id": task_id})
    return entries


def _stored_media_entry(kind: str, media: object, result: dict[str, object]) -> dict[str, object] | None:
    if not isinstance(media, str) or parse_media_reference(media) is None:
        return None
    entry: dict[str, object] = {"kind": kind, "media": media}
    model = result.get("model")
    if isinstance(model, str) and model:
        entry["model"] = model
    return entry


def _image_edit_entries(result: dict[str, object]) -> list[dict[str, object]]:
    images = result.get("images")
    if not isinstance(images, list):
        return []
    entries = (_stored_media_entry("image", image.get("url"), result) for image in images if isinstance(image, dict))
    return [entry for entry in entries if entry is not None]


def _speech_entries(result: dict[str, object]) -> list[dict[str, object]]:
    if result.get("status") != "success":
        return []
    entry = _stored_media_entry("tts", result.get("audio_url"), result)
    if entry is None:
        return []
    duration = result.get("duration_seconds")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        entry["duration_seconds"] = duration
    return [entry]


def collect_media_generated(entries: list[dict[str, object]], event: dict[str, object]) -> None:
    """Append what a ``tool_end`` event of a media tool registers; any other event adds nothing."""
    tool_name = event.get("tool_name")
    if tool_name not in (_IMAGE_TOOL, _VIDEO_TOOL, _TTS_TOOL):
        return
    result = parse_tool_end_result(event)
    if not isinstance(result, dict):
        return

    if tool_name == _TTS_TOOL:
        found = _speech_entries(result)
    elif tool_name == _VIDEO_TOOL:
        found = _task_entries("video", result)
    else:
        found = _task_entries("image", result) or _image_edit_entries(result)
    for entry in found:
        if entry not in entries:
            entries.append(entry)
