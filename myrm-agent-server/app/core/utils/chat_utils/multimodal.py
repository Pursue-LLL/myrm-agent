"""[INPUT]
- myrm_agent_harness.utils.chat_utils / image_utils / json_parsing (POS: framework primitives)

[OUTPUT]
- preprocess_inbound_multimodal_query and the per-item dispatcher _process_human_content.

[POS]
Chat helper module: inbound multimodal query preprocessing.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.chat_utils import (
    ContentItem,
)

from .image_items import _process_image_item
from .video_items import _process_video_item

logger = logging.getLogger(__name__)


async def preprocess_inbound_multimodal_query(
    query: str | list[dict[str, object]],
    *,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
    vision_fallback_model_cfgs: object | None = None,
    meta: dict[str, object] | None = None,
) -> str | list[dict[str, object]]:
    """Apply vision fallback preprocessing for non-Web inbound multimodal queries."""
    if not isinstance(query, list):
        return query

    has_images = any(isinstance(item, dict) and item.get("type") == "image_url" for item in query)
    if not has_images:
        return query

    supports_vision = getattr(model_cfg, "supports_vision", False) if model_cfg else True
    if supports_vision or (vision_fallback_model_cfg is None and vision_fallback_model_cfgs is None):
        return query

    return await _process_human_content(
        query,
        meta=meta or {},
        model_cfg=model_cfg,
        vision_fallback_model_cfg=vision_fallback_model_cfg,
        vision_fallback_model_cfgs=vision_fallback_model_cfgs,
    )


async def _process_human_content(
    content: ContentItem,
    meta: dict[str, object] = None,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
    vision_fallback_model_cfgs: object | None = None,
    video_fallback_model_cfgs: object | None = None,
) -> str | list[str | dict[str, object]]:
    """处理人类消息内容，支持文本和图片，使用 asyncio.gather 并发提升多图处理性能"""
    if meta is None:
        meta = {}
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        import asyncio

        has_media = any(
            isinstance(item, dict) and item.get("type") in ("image_url", "image", "video_url", "video") for item in content
        )
        has_text_content = any(
            isinstance(item, dict) and item.get("type") == "text" and str(item.get("text") or "").strip() for item in content
        )

        tasks = []
        replaced_empty_text = False
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    tasks.append(
                        _process_image_item(
                            item,
                            meta,
                            model_cfg,
                            vision_fallback_model_cfg,
                            vision_fallback_model_cfgs,
                        )
                    )
                elif item.get("type") == "video_url":
                    tasks.append(
                        _process_video_item(
                            item,
                            meta,
                            model_cfg,
                            vision_fallback_model_cfg,
                            vision_fallback_model_cfgs,
                            video_fallback_model_cfgs,
                        )
                    )
                elif item.get("type") == "text":
                    text_val = str(item.get("text") or "").strip()
                    if not text_val and has_media and not has_text_content and not replaced_empty_text:
                        item = {"type": "text", "text": "请分析附带的媒体内容。"}
                        replaced_empty_text = True

                    async def _return_item(i=item):
                        return i

                    tasks.append(_return_item())
                else:

                    async def _return_item(i=item):
                        return i

                    tasks.append(_return_item())
            else:

                async def _return_item(i=item):
                    return {"type": "text", "text": str(i)}

                tasks.append(_return_item())

        processed_items = await asyncio.gather(*tasks) if tasks else []
        if has_media and not has_text_content and not replaced_empty_text:
            processed_items.insert(0, {"type": "text", "text": "请分析附带的媒体内容。"})

        # 检查是否执行过图像/视频分析，若执行过，需要发送状态清除指令并统一更新 DB
        if (meta.get("_analyzed_image") or meta.get("_analyzed_video")) and meta.get("chat_id"):
            # 统一执行一次 DB 更新，避免多图时产生 DB 写风暴
            message_id = meta.get("message_id")
            if message_id and isinstance(message_id, str):
                import asyncio

                from app.services.chat.chat_service import ChatService

                extra_data = meta.get("extra_data", {})
                asyncio.create_task(ChatService.update_message_extra_data(message_id, extra_data))

            chat_id = meta.get("chat_id")
            from app.services.event.app_event_bus import (
                AppEvent,
                AppEventType,
                get_event_bus,
            )

            bus = get_event_bus()
            bus.publish(
                AppEvent(
                    event_type=AppEventType.ASYNC_AGENT_STREAM_CHUNK,
                    data={
                        "session_id": chat_id,
                        "chunk": {
                            "type": "agent_status",
                            "messageId": meta.get("message_id") or "system",
                            "data": {
                                "status": "clear",
                            },
                        },
                    },
                )
            )

        return list(processed_items)

    return str(content)
