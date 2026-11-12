"""[INPUT]
- myrm_agent_harness.utils.chat_utils / image_utils / json_parsing (POS: framework primitives)

[OUTPUT]
- _process_video_item: extract frames and build the vision payload.

[POS]
Chat helper module: video content-item conversion.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def _process_video_item(
    item: dict[str, object],
    meta: dict[str, object] = None,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
    vision_fallback_model_cfgs: object | None = None,
    video_fallback_model_cfgs: object | None = None,
) -> dict[str, object]:
    """Process a video content item.

    If the model supports native video, passes the video_url through as-is.
    Otherwise, uses VideoAnalysisEngine to extract frames and generate a
    text description via vision fallback model.
    Uses MD5 hash-based caching to avoid redundant analysis on the same video.
    """
    if meta is None:
        meta = {}
    try:
        import hashlib

        raw_vu = item.get("video_url")
        vu_dict = raw_vu if isinstance(raw_vu, dict) else {}
        url_raw = vu_dict.get("url", "")
        video_url = str(url_raw) if url_raw is not None else ""

        if not video_url:
            return item

        supports_video = getattr(model_cfg, "supports_video", False) if model_cfg else False

        video_hash = hashlib.md5(video_url.encode("utf-8")).hexdigest()

        from app.core.vision.media_router import (
            pick_video_fallback_configs,
            resolve_video_route,
        )

        video_cfgs = list(video_fallback_model_cfgs) if isinstance(video_fallback_model_cfgs, list) else []
        vision_cfgs = list(vision_fallback_model_cfgs) if isinstance(vision_fallback_model_cfgs, list) else []
        route = resolve_video_route(
            supports_video=supports_video,
            has_video_fallback=bool(video_cfgs),
            has_vision_fallback=bool(vision_cfgs or vision_fallback_model_cfg),
        )
        cache_key = f"{video_hash}:{route.cache_namespace}"
        extra_data = meta.get("extra_data", {}) if isinstance(meta.get("extra_data"), dict) else {}

        if not supports_video and (vision_fallback_model_cfg is not None or vision_fallback_model_cfgs is not None or video_cfgs):
            video_cache = extra_data.get("video_cache", {})
            if cache_key in video_cache:
                return {"type": "text", "text": video_cache[cache_key]}

        if supports_video:
            mime = str(vu_dict.get("mime_type", "video/mp4"))
            return {
                "type": "image_url",
                "image_url": {"url": video_url},
                "_mime_type": mime,
            }

        if vision_fallback_model_cfg or vision_fallback_model_cfgs or video_cfgs:
            from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
                resolve_vision_fallback_llm_configs,
            )
            from myrm_agent_harness.toolkits.llms.vision.video_analysis_engine import (
                VideoAnalysisEngine,
            )

            try:
                fallback_configs = pick_video_fallback_configs(video_cfgs, vision_cfgs)
                if not fallback_configs:
                    fallback_configs = resolve_vision_fallback_llm_configs(
                        vision_fallback_model_cfg,
                        vision_fallback_model_cfgs,
                    )
                engine = VideoAnalysisEngine(fallback_configs)

                meta["_analyzed_video"] = True

                chat_id = meta.get("chat_id")
                if chat_id:
                    from app.services.event.app_event_bus import (
                        AppEvent,
                        AppEventType,
                        get_event_bus,
                    )

                    bus = get_event_bus()
                    status_data: dict[str, object] = {
                        "status": "analyzing_video",
                        "message": "Analyzing video content...",
                    }
                    if route.backend_badge:
                        status_data["vision_backend"] = route.backend_badge
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

                use_native = route.use_native_video or any(getattr(cfg, "supports_video", False) for cfg in fallback_configs)
                fallback_text = await engine.analyze_video_url(
                    video_url,
                    supports_video=use_native,
                    native_video_required=route.native_video_required,
                )
                fallback_text = f"[Video Analysis]:\n{fallback_text}"

                message_id = meta.get("message_id")
                if message_id and isinstance(message_id, str):
                    if "video_cache" not in extra_data:
                        extra_data["video_cache"] = {}
                    extra_data["video_cache"][cache_key] = fallback_text

                return {"type": "text", "text": fallback_text}
            except Exception as e:
                logger.warning("Video analysis fallback failed: %s", e)
                return {
                    "type": "text",
                    "text": "[Video could not be analyzed]",
                }

        return {
            "type": "text",
            "text": "[Video attached — current model does not support native video analysis. "
            "Configure a vision fallback model for video frame analysis.]",
        }

    except Exception as e:
        logger.warning("Error processing video item: %s", e)
        return item
