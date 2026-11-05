"""[INPUT]
- myrm_agent_harness.utils.chat_utils / image_utils / json_parsing (POS: framework primitives)
- app.core.utils.files_utils::read_image_as_base64 (POS: image read helper)

[OUTPUT]
- _process_image_item: local URL → base64, compression and vision fallback.

[POS]
Chat helper module: image content-item conversion.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.image_utils import (
    MAX_IMAGE_PAYLOAD_BYTES,
    MAX_IMAGE_READ_BYTES,
    estimate_base64_byte_size,
    is_base64_data_url,
)
from myrm_agent_harness.utils.url_utils import is_image_url, is_valid_image_url

from app.core.utils.files_utils import read_image_as_base64

from .images import _compress_base64_image, _needs_compression_base64

logger = logging.getLogger(__name__)


async def _process_image_item(
    item: dict[str, object],
    meta: dict[str, object] = None,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
    vision_fallback_model_cfgs: object | None = None,
) -> dict[str, object]:
    """处理图片项目，转换本地 URL 为 base64 格式。

    Applies a MAX_IMAGE_BYTES size limit (aligned with image_reader.py).
    Images exceeding the limit are replaced with a text description.
    Also handles Text-Mode Vision Fallback if the main model does not support vision.
    Uses MD5 dict-based extra_data caching to prevent overwrites on multiple images.
    """
    if meta is None:
        meta = {}
    try:
        import hashlib

        raw_iu = item.get("image_url")
        iu_dict = raw_iu if isinstance(raw_iu, dict) else {}
        if isinstance(raw_iu, dict) and raw_iu.get("detail") == "auto":
            del raw_iu["detail"]
        url_raw = iu_dict.get("url", "")
        image_url = str(url_raw) if url_raw is not None else ""

        if not image_url:
            return item

        if not (is_image_url(image_url) or is_base64_data_url(image_url)):
            return item

        supports_vision = getattr(model_cfg, "supports_vision", False) if model_cfg else True

        # 计算图片哈希用于字典缓存隔离
        img_hash = hashlib.md5(image_url.encode("utf-8")).hexdigest()
        cache_key = f"{img_hash}:chat_fallback"
        extra_data = meta.get("extra_data", {}) if isinstance(meta.get("extra_data"), dict) else {}

        if not supports_vision and vision_fallback_model_cfg:
            vision_cache = extra_data.get("vision_cache", {})
            if cache_key in vision_cache:
                return {"type": "text", "text": vision_cache[cache_key]}

        if is_base64_data_url(image_url):
            byte_size = estimate_base64_byte_size(image_url)
            if byte_size > MAX_IMAGE_READ_BYTES:
                logger.warning("Image too large to read (%d bytes), degrading to text", byte_size)
                return {
                    "type": "text",
                    "text": f"[Image too large: {byte_size / 1024 / 1024:.1f}MB, limit {MAX_IMAGE_READ_BYTES // 1024 // 1024}MB]",
                }
            base64_data = image_url.split(",")[1]
            mime_type = image_url.split(";")[0].split(":")[1]
            if _needs_compression_base64(base64_data, byte_size):
                compressed = _compress_base64_image(base64_data)
                if compressed is not None:
                    base64_data = compressed
                    mime_type = "image/jpeg"
                    data_url = f"data:{mime_type};base64,{base64_data}"
                    byte_size = estimate_base64_byte_size(data_url)
            else:
                data_url = image_url

            if byte_size > MAX_IMAGE_PAYLOAD_BYTES:
                return {
                    "type": "text",
                    "text": f"[Image too large after compression: {byte_size / 1024 / 1024:.1f}MB, limit {MAX_IMAGE_PAYLOAD_BYTES // 1024 // 1024}MB]",
                }
        elif not is_valid_image_url(image_url):
            base64_data, mime_type = await read_image_as_base64(image_url)
            data_url = f"data:{mime_type};base64,{base64_data}"
            byte_size = estimate_base64_byte_size(data_url)
            if byte_size > MAX_IMAGE_READ_BYTES:
                logger.warning(
                    "Converted image too large to read (%d bytes), degrading to text",
                    byte_size,
                )
                return {
                    "type": "text",
                    "text": f"[Image too large: {byte_size / 1024 / 1024:.1f}MB, limit {MAX_IMAGE_READ_BYTES // 1024 // 1024}MB]",
                }
            if _needs_compression_base64(base64_data, byte_size):
                compressed = _compress_base64_image(base64_data)
                if compressed is not None:
                    base64_data = compressed
                    mime_type = "image/jpeg"
                    data_url = f"data:{mime_type};base64,{base64_data}"
                    byte_size = estimate_base64_byte_size(data_url)

            if byte_size > MAX_IMAGE_PAYLOAD_BYTES:
                return {
                    "type": "text",
                    "text": f"[Image too large after compression: {byte_size / 1024 / 1024:.1f}MB, limit {MAX_IMAGE_PAYLOAD_BYTES // 1024 // 1024}MB]",
                }
        else:
            return item

        if not supports_vision and (vision_fallback_model_cfg is not None or vision_fallback_model_cfgs is not None):
            from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
                create_vision_fallback_engine,
            )

            try:
                engine = create_vision_fallback_engine(
                    vision_fallback_model_cfg,
                    vision_fallback_model_cfgs,
                )
                if engine is None:
                    raise ValueError("Vision fallback engine is not configured")

                # 标记该 meta 经历了图像分析，用于外部清除状态
                meta["_analyzed_image"] = True

                chat_id = meta.get("chat_id")
                if chat_id:
                    from app.core.vision.media_router import resolve_image_route
                    from app.services.event.app_event_bus import (
                        AppEvent,
                        AppEventType,
                        get_event_bus,
                    )

                    image_route = resolve_image_route(
                        supports_vision=supports_vision,
                        has_fallback=True,
                    )
                    bus = get_event_bus()
                    status_data: dict[str, object] = {
                        "status": "analyzing_image",
                        "message": "Analyzing image with vision model...",
                    }
                    if image_route.backend_badge:
                        status_data["vision_backend"] = image_route.backend_badge
                    bus.publish(
                        AppEvent(
                            event_type=AppEventType.ASYNC_AGENT_STREAM_CHUNK,
                            data={
                                "session_id": chat_id,
                                "chunk": {
                                    "type": "agent_status",
                                    "messageId": meta.get("message_id") or "system",
                                    "data": status_data,
                                },
                            },
                        )
                    )

                fallback_text = await engine.describe_image_b64(base64_data, mime_type)
                fallback_text = f"[Image Analysis]:\n{fallback_text}"

                # Update in-memory extra_data using hash dictionary
                # DB update is batched in _process_human_content to avoid write storms
                message_id = meta.get("message_id")
                if message_id and isinstance(message_id, str):
                    if "vision_cache" not in extra_data:
                        extra_data["vision_cache"] = {}
                    extra_data["vision_cache"][cache_key] = fallback_text

                return {"type": "text", "text": fallback_text}
            except Exception as e:
                logger.warning(f"Vision fallback failed: {e}")
                return {
                    "type": "text",
                    "text": "[Image could not be analyzed]",
                }

        return {"type": "image_url", "image_url": {"url": data_url}}

    except Exception as e:
        logger.warning(f"Error processing image item: {e}")
        return item
