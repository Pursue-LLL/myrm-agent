"""Sticker visual understanding via Vision model.

Provides an LRU-cached service that converts sticker images into text
descriptions using VisionFallbackEngine. Only static stickers (.webp) are
supported; animated (.tgs) and video (.webm) stickers are skipped.

Integration follows the same pattern as voice STT in
``channels.voice.handler.transcribe_inbound``: a pure async function
that enriches an ``InboundMessage`` and is called from Router._handle_merged.

[INPUT]
- vision.fallback_engine::VisionFallbackEngine (POS: image-to-text engine)
- channels.types::InboundMessage (POS: inbound message dataclass)

[OUTPUT]
- StickerVisionService: sticker description service with LRU cache
- describe_sticker_inbound(): enrich InboundMessage with sticker description

[POS]
Sticker visual understanding service for channel media enrichment.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Protocol

from app.channels.types import InboundMessage

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.vision.fallback_engine import VisionFallbackEngine

logger = logging.getLogger(__name__)

_LRU_MAX_SIZE = 512
_DESCRIBE_TIMEOUT = 10.0

_STICKER_PROMPT = (
    "Describe this sticker image in 1-2 concise sentences. "
    "Focus on what it depicts: the character, object, action, and emotion. "
    "Be objective and descriptive. Output ONLY the description."
)


def _build_sticker_prompt(set_name: str) -> str:
    """Build a sticker-specific vision prompt, optionally including set context."""
    if set_name:
        return f"This is a sticker from the '{set_name}' sticker pack. {_STICKER_PROMPT}"
    return _STICKER_PROMPT


class StickerDownloader(Protocol):
    """Protocol for downloading sticker file bytes by file_id."""

    async def get_file(self, file_id: str) -> dict[str, object]: ...
    async def download_file(self, file_path: str, *, timeout: float = 30.0) -> bytes: ...


class StickerVisionService:
    """Sticker visual understanding with LRU cache.

    Uses VisionFallbackEngine to describe static sticker images.
    Animated and video stickers are skipped (returns None).
    Results are cached by file_unique_id (Telegram-global identifier).
    """

    def __init__(self, engine: VisionFallbackEngine, max_cache_size: int = _LRU_MAX_SIZE) -> None:
        self._engine = engine
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._in_flight: dict[str, asyncio.Future[str | None]] = {}

    async def describe(
        self,
        file_id: str,
        file_unique_id: str,
        downloader: StickerDownloader,
        *,
        set_name: str = "",
        is_animated: bool = False,
        is_video: bool = False,
    ) -> str | None:
        """Describe a sticker image, returning cached result when available.

        Returns None for animated/video stickers or on failure.
        Deduplicates concurrent requests for the same file_unique_id.
        """
        if is_animated or is_video:
            return None

        if not file_unique_id:
            return None

        cached = self._cache.get(file_unique_id)
        if cached is not None:
            self._cache.move_to_end(file_unique_id)
            return cached

        existing = self._in_flight.get(file_unique_id)
        if existing is not None:
            return await existing

        fut: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self._in_flight[file_unique_id] = fut
        try:
            result = await self._fetch_and_cache(file_id, file_unique_id, set_name, downloader)
            fut.set_result(result)
            return result
        except BaseException as exc:
            fut.set_exception(exc)
            raise
        finally:
            self._in_flight.pop(file_unique_id, None)

    async def _fetch_and_cache(
        self,
        file_id: str,
        file_unique_id: str,
        set_name: str,
        downloader: StickerDownloader,
    ) -> str | None:
        """Download, describe, and cache a sticker. Returns None on failure."""
        try:
            description = await asyncio.wait_for(
                self._download_and_describe(file_id, set_name, downloader),
                timeout=_DESCRIBE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning("Sticker vision timed out for %s", file_unique_id)
            return None
        except Exception as exc:
            logger.warning("Sticker vision failed for %s: %s", file_unique_id, exc)
            return None

        if description and not description.startswith("[Vision Analysis Failed"):
            self._put_cache(file_unique_id, description)
            return description

        return None

    async def _download_and_describe(
        self,
        file_id: str,
        set_name: str,
        downloader: StickerDownloader,
    ) -> str:
        """Download sticker via Telegram API and describe with vision model."""
        file_info = await downloader.get_file(file_id)
        file_path = str(file_info.get("file_path", ""))
        if not file_path:
            raise ValueError("Empty file_path from getFile")

        raw_bytes = await downloader.download_file(file_path, timeout=_DESCRIBE_TIMEOUT)
        b64_data = base64.b64encode(raw_bytes).decode("ascii")

        prompt = _build_sticker_prompt(set_name)
        return await self._engine.describe_image_b64(b64_data, "image/webp", prompt=prompt)

    def _put_cache(self, key: str, value: str) -> None:
        """Insert into LRU cache with eviction."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
            return
        if len(self._cache) >= self._max_cache_size:
            self._cache.popitem(last=False)
        self._cache[key] = value

    @property
    def cache_size(self) -> int:
        return len(self._cache)


async def describe_sticker_inbound(
    msg: InboundMessage,
    sticker_vision: StickerVisionService | None,
    get_channel_fn: object,
) -> InboundMessage:
    """Enrich an InboundMessage with sticker visual description.

    Follows the same pattern as ``transcribe_inbound`` in voice handler.
    Returns the original message unchanged if not a sticker or on failure.
    """
    if sticker_vision is None:
        return msg

    if not msg.metadata.get("is_sticker"):
        return msg

    is_animated = bool(msg.metadata.get("sticker_is_animated"))
    is_video = bool(msg.metadata.get("sticker_is_video"))
    if is_animated or is_video:
        return msg

    file_id = msg.metadata.get("sticker_file_id")
    file_unique_id = msg.metadata.get("sticker_file_unique_id")
    if not isinstance(file_id, str) or not isinstance(file_unique_id, str):
        return msg

    if not callable(get_channel_fn):
        return msg
    ch = get_channel_fn(msg.channel)
    if ch is None or not hasattr(ch, "_client"):
        return msg

    set_name = msg.metadata.get("sticker_set_name", "")
    emoji = msg.metadata.get("sticker_emoji", "")

    description = await sticker_vision.describe(
        file_id=file_id,
        file_unique_id=file_unique_id,
        downloader=ch._client,  # type: ignore[arg-type]
        set_name=str(set_name),
        is_animated=is_animated,
        is_video=is_video,
    )

    if not description:
        return msg

    sticker_text = f"[Sticker: {description}]"
    if emoji:
        sticker_text = f"{sticker_text} {emoji}"

    logger.warning("Sticker: vision described %s → %d chars", file_unique_id, len(description))
    return dataclasses.replace(msg, content=sticker_text)
