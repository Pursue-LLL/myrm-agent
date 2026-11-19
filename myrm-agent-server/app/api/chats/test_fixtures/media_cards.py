"""Local-only media cards Chrome E2E seed route.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
- app.ai_agents.media_tools.media_persist::create_media_persist_callback (POS: the production store-and-reference path)
- app.core.media.reference::parse_media_reference (POS: ``media://<id>`` artifact identity)
- app.tasks.executors.image_executor::image_task_result (POS: the result shape of a finished image task)
- app.lifecycle.task_worker::get_task_store (POS: live task store of the running server)
- app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
- app.services.chat.chat_service::ChatService (POS: chat/message persistence)

[OUTPUT]
- seed_media_cards_fixture: a chat whose assistant reply registered one generated media of the requested kind

[POS]
Mounted via test_fixtures/__init__.py router include. The media goes through the same store-and-reference path the
engines use and the message carries the entry a media tool's result registers, so the cards load real files the way a
finished turn leaves them, beside a reply that also says something in words. ``address`` swaps what a task result
points at: an address no browser can load (the negative control of the load probe) or a task record that is gone.
"""

from __future__ import annotations

import base64
import io
import wave
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.llms.image import MediaMeta
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_IMAGE_GENERATE, TASK_TYPE_VIDEO_GENERATE
from myrm_agent_harness.toolkits.llms.video import VideoAsset, VideoResult
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.ai_agents.media_tools.media_persist import create_media_persist_callback
from app.config.deploy_mode import is_local_mode
from app.core.media.reference import parse_media_reference
from app.database.dto import ChatCreate
from app.lifecycle.task_worker import get_task_store
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.tasks.executors.image_executor import image_task_result

router = APIRouter()

MediaKind = Literal["image", "video", "image_edit", "tts"]
MediaAddress = Literal["media", "file", "expired"]

_MODEL = "e2e-fixture"
_PROMPT = "MYRM_E2E_MEDIA_CARD_PROMPT"
_REPLY_TEXT = "MYRM_E2E_MEDIA_CARD_REPLY"
# Part of the address a task result points at when ``address=file``; the card's media element carries it in ``src``.
_UNREACHABLE_MARKER = "myrm-e2e-media-unreachable"
_IMAGE_SIDE = 64
_SPEECH_SECONDS = 1

# One second of 32x32 VP8: the smallest clip every Chromium build plays, so no encoder runs at request time.
_CLIP_WEBM_BASE64 = (
    "GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQJChYECGFOAZwEAAAAAAANPEU2bdLpNu4tTq4QVSalmU6yBoU27i1Or"
    "hBZUrmtTrIHYTbuMU6uEElTDZ1OsggEbTbuMU6uEHFO7a1OsggM57AEAAAAAAABZAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVSalmsirX"
    "sYMPQkBNgI1MYXZmNjIuMTIuMTAyV0GNTGF2ZjYyLjEyLjEwMkSJiECPQAAAAAAAFlSua76uAQAAAAAAADXXgQFzxYixebTq"
    "5XXZTJyBACK1nIN1bmSIgQCGhVZfVlA4g4EBI+ODhAX14QDghrCBILqBIBJUw2fYc3OgY8CAZ8iaRaOHRU5DT0RFUkSHjUxh"
    "dmY2Mi4xMi4xMDJzc7JjwItjxYixebTq5XXZTGfIoUWjiERVUkFUSU9ORIeTMDA6MDA6MDEuMDAwMDAwMDAwAB9DtnVBu+eB"
    "AKO9gQAAgNACAJ0BKiAAIAAARwiFhYiFhIgCAgJ1qgP4AgghCD0A/v9NEv/8WFfxYV/FhX/xYV/8/M7txfzmAKOogQBkAPEB"
    "AAEQEAAYAB5R//QAh/2AAP7e1j/zBK/IN2of/G7cYb70AKOogQDIAPEBAAEQEAAYAB5R//QAh/2AAP7e1j/ylXgsbo8/+IZ6"
    "PUxgAKOogQEsAPEBAAEQEAAYAB5R//QAh/2AAP7e1j/zBK/IN2of/G7cYb70AKOogQGQAPEBAAEQEAAYAB5R//QAh/2AAP7e"
    "1j/zBK/IN2of/G7cYb70AKOogQH0APEBAAEQEAAYAB5R//QAh/2AAP7e1j/ylXgsbo8/+N24w33oAKOogQJYAPEBAAEQEAAY"
    "AB5R//QAh/2AAP7e1j/zBK/IN2of/EM9HqYwAKOngQK8ANEBAAEQEBRgAHlH/9ACH/YA/t7WP/MEr8g3ah/8btxhvvQAo6iB"
    "AyAA8QEAARAQABgAHlH/9ACH/YAA/t7WP/MEr8g3ah/8btxhvvQAo6iBA4QA8QEAARAQABgAHlH/9ACH/YAA/t7WP/KVeCxu"
    "jz/43bjDfegAHFO7a5G7j7OBALeK94EB8YIBePCBAw=="
)


def _fixture_png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (_IMAGE_SIDE, _IMAGE_SIDE), (46, 92, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _fixture_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000 * _SPEECH_SECONDS)
    return buffer.getvalue()


def _asset(kind: MediaKind) -> tuple[bytes, str]:
    if kind == "video":
        return base64.b64decode(_CLIP_WEBM_BASE64), "video/webm"
    if kind == "tts":
        return _fixture_wav(), "audio/wav"
    return _fixture_png(), "image/png"


async def _store(chat_id: str, kind: MediaKind) -> str:
    """Store the kind's media through the production persist callback and return its ``media://`` reference."""
    data, mime_type = _asset(kind)
    persist = create_media_persist_callback(chat_id=chat_id, model_name=_MODEL, source="e2e-fixture")
    return await persist(data, mime_type, MediaMeta(prompt=_PROMPT, model=_MODEL))


def _task_result(kind: Literal["image", "video"], reference: str) -> dict[str, object]:
    if kind == "image":
        return image_task_result(reference, "image/png", prompt=_PROMPT, model=_MODEL, latency_ms=1)
    data, mime_type = _asset("video")
    result = VideoResult(
        videos=[VideoAsset(data=data, mime_type=mime_type)],
        provider=_MODEL,
        model=_MODEL,
        latency_ms=1,
        persisted_refs=[reference],
    )
    return {**result.to_dict(), "prompt": _PROMPT}


async def _register_task(
    chat_id: str, kind: Literal["image", "video"], address: MediaAddress
) -> tuple[dict[str, object], str | None]:
    """The registered entry of an async generation and the marker its media element carries in ``src``."""
    task_id = f"{kind}-e2e-{uuid4().hex[:8]}"
    entry: dict[str, object] = {"kind": kind, "task_id": task_id}
    if address == "expired":
        return entry, None

    marker: str | None
    if address == "file":
        reference, marker = f"file:///var/empty/{_UNREACHABLE_MARKER}", _UNREACHABLE_MARKER
    else:
        reference = await _store(chat_id, kind)
        marker = parse_media_reference(reference)
    now = datetime.now(UTC)
    await get_task_store().create_task(
        Task(
            task_id=task_id,
            task_type=TASK_TYPE_IMAGE_GENERATE if kind == "image" else TASK_TYPE_VIDEO_GENERATE,
            user_id="local",
            status=TaskStatus.SUCCEEDED,
            payload={"prompt": _PROMPT, "chat_id": chat_id},
            started_at=now,
            completed_at=now,
            progress=1.0,
            result=_task_result(kind, reference),
        )
    )
    return entry, marker


async def _register_stored(chat_id: str, kind: Literal["image_edit", "tts"]) -> tuple[dict[str, object], str | None]:
    """The registered entry of a synchronous generation, which names the stored media itself."""
    reference = await _store(chat_id, kind)
    if kind == "tts":
        entry: dict[str, object] = {
            "kind": "tts",
            "media": reference,
            "model": _MODEL,
            "duration_seconds": _SPEECH_SECONDS,
        }
    else:
        entry = {"kind": "image", "media": reference, "model": _MODEL}
    return entry, parse_media_reference(reference)


@router.post("/test/seed-media-cards-fixture", include_in_schema=False)
async def seed_media_cards_fixture(kind: MediaKind, address: MediaAddress = "media") -> dict[str, object]:
    """Local dev/test only: seed a chat whose assistant reply registered one generated media."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")
    if address != "media" and kind not in ("image", "video"):
        raise HTTPException(status_code=400, detail="Only a task card can point at an unreachable or expired result")

    agents, _total = await AgentService.get_agent_list(1, 100)
    chat_id = f"e2emedia{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Media cards Chrome E2E",
            agent_id=agents[0].id if agents else None,
            messages=[],
        )
    )

    if kind == "image" or kind == "video":
        entry, marker = await _register_task(chat_id, kind, address)
    else:
        entry, marker = await _register_stored(chat_id, kind)

    now = datetime.now(UTC)
    await ChatService.append_message(chat_id, "user", _PROMPT, now, "UTC")
    await ChatService.append_message(chat_id, "assistant", _REPLY_TEXT, now, "UTC", extra_data={"media_generated": [entry]})
    return {"chat_id": chat_id, "kind": kind, "address": address, "entry": entry, "marker": marker, "ui_path": f"/{chat_id}"}
