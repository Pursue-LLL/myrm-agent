"""聊天工具函数模块（业务层扩展）

扩展框架层的聊天工具，添加图片处理、视频处理和 Agent 历史还原等业务功能
"""

import json
import logging
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from myrm_agent_harness.utils.chat_utils import (
    ChatHistory,
    ChatHistoryReq,
    ContentItem,
)
from myrm_agent_harness.utils.image_utils import (
    MAX_IMAGE_PAYLOAD_BYTES,
    MAX_IMAGE_READ_BYTES,
    content_has_images,
    estimate_base64_byte_size,
    is_base64_data_url,
    strip_images_from_content,
)
from myrm_agent_harness.utils.url_utils import is_image_url, is_valid_image_url

from app.core.utils.files_utils import read_image_as_base64

logger = logging.getLogger(__name__)

_INLINE_COMPRESS_THRESHOLD = 5 * 1024 * 1024

__all__ = [
    "ChatHistory",
    "ChatHistoryReq",
    "ContentItem",
    "convert_chat_history",
]

# =============================================================================
# Agent History Expansion
# =============================================================================


def _try_parse_agent_history(content: str) -> dict[str, object] | None:
    """尝试解析 __agent_history JSON 标记。返回 None 表示普通文本。"""
    if not content.startswith('{"__agent_history"'):
        return None
    try:
        data = json.loads(content)
        if isinstance(data, dict) and data.get("__agent_history") is True:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _build_tool_result_text(tool_name: str, sources: list[dict[str, object]]) -> str:
    """从 sources 数据构建 ToolMessage 的结果文本"""
    if "search" in tool_name.lower():
        lines = []
        for s in sources:
            if s.get("type") in ("web_search", "web_fetch"):
                title = s.get("title", "Untitled")
                url = s.get("url", "")
                snippet = s.get("snippet", "")
                entry = f"[{s.get('index', '?')}] {title}\n    URL: {url}"
                if snippet:
                    entry += f"\n    {snippet}"
                lines.append(entry)
        return "\n\n".join(lines) if lines else "Search completed with results."

    if any(kw in tool_name.lower() for kw in ("fetch", "browse", "webpage")):
        urls = [str(s.get("url", "")) for s in sources if s.get("type") == "web_fetch" and s.get("url")]
        return f"Fetched content from: {', '.join(urls)}" if urls else "Web page content fetched."

    if "skill" in tool_name.lower() or "mcp" in tool_name.lower():
        skills = [str(s.get("skill_name", "")) for s in sources if s.get("type") == "mcp" and s.get("skill_name")]
        return f"MCP skills executed: {', '.join(skills)}" if skills else "Skill executed successfully."

    return f"Tool '{tool_name}' completed successfully."


def _expand_agent_history(content: str) -> list[BaseMessage]:
    """将 __agent_history JSON 还原为 LangGraph 原生消息序列。

    输出: AIMessage(tool_calls=[...]) + ToolMessage(...) × N + AIMessage(content=...)
    这样 LangGraph Agent 在后续决策时能原生识别之前的工具调用历史。
    """
    data = _try_parse_agent_history(content)
    if data is None:
        return [AIMessage(content=content)]

    messages: list[BaseMessage] = []
    tool_calls_data: list[dict[str, object]] = data.get("tool_calls", [])  # type: ignore[assignment]
    sources: list[dict[str, object]] = data.get("sources", [])  # type: ignore[assignment]
    text_content: str = data.get("content", "")  # type: ignore[assignment]

    if tool_calls_data:
        lc_tool_calls: list[dict[str, object]] = []
        tool_messages: list[ToolMessage] = []

        for tc in tool_calls_data:
            tc_id = f"hist_{uuid4().hex[:8]}"
            tc_name = str(tc.get("name", "unknown"))
            tc_args = tc.get("args", {})

            lc_tool_calls.append(
                {
                    "name": tc_name,
                    "args": tc_args if isinstance(tc_args, dict) else {},
                    "id": tc_id,
                    "type": "tool_call",
                }
            )

            result_text = _build_tool_result_text(tc_name, sources)
            tool_messages.append(
                ToolMessage(
                    content=result_text,
                    tool_call_id=tc_id,
                    name=tc_name,
                )
            )

        messages.append(AIMessage(content="", tool_calls=lc_tool_calls))
        messages.extend(tool_messages)

    if text_content:
        messages.append(AIMessage(content=text_content))
    elif not messages:
        messages.append(AIMessage(content=""))

    return messages


# =============================================================================
# Chat History Conversion
# =============================================================================

_MAX_IMAGE_TURNS = 2


async def convert_chat_history(
    history: object,
    max_image_turns: int = _MAX_IMAGE_TURNS,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
) -> ChatHistory:
    """将聊天历史转换为 LangChain 消息格式

    支持：
    - 图片内容处理（human 消息）
    - Agent 工具历史还原（assistant 消息中的 __agent_history JSON）
    - 历史图片降级：仅保留最近 max_image_turns 个 turn 的图片，
      更旧的 turn 中的图片替换为文本占位符（节省上下文窗口）

    Args:
        history: 原始格式 [["human", content], ["assistant", content], ...]
                或已转换格式 [HumanMessage, AIMessage, ...]
        max_image_turns: 保留图片的最大 turn 数（从最新往回计）
    """
    if not history:
        return []

    if isinstance(history, list) and history and isinstance(history[0], BaseMessage):
        return history

    if not isinstance(history, list):
        return []

    messages: list[BaseMessage] = []
    for item in history:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role, content = item[0], item[1]

        if role == "human":
            meta = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            processed_content = await _process_human_content(content, meta, model_cfg, vision_fallback_model_cfg)
            messages.append(HumanMessage(content=processed_content))
        else:
            assistant_meta = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            text_content = str(content) if not isinstance(content, str) else content
            expanded = _expand_agent_history(text_content)
            reasoning_content = assistant_meta.get("reasoning_content")
            if isinstance(reasoning_content, str) and reasoning_content and expanded:
                for msg in expanded:
                    if isinstance(msg, AIMessage):
                        msg.additional_kwargs["reasoning_content"] = reasoning_content
                        break
            messages.extend(expanded)

    _degrade_old_images(messages, max_image_turns)

    return messages


def _degrade_old_images(messages: list[BaseMessage], max_image_turns: int) -> None:
    """Replace images in older turns with text placeholders (in-place).

    Traverses messages from newest to oldest. Only the most recent
    max_image_turns HumanMessages with images keep their original content;
    older ones get their images stripped.
    """
    image_turns_seen = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, HumanMessage):
            continue
        if not content_has_images(msg.content):
            continue

        image_turns_seen += 1
        if image_turns_seen > max_image_turns:
            msg.content = strip_images_from_content(msg.content)


# =============================================================================
# Image Compression Helpers
# =============================================================================


def _needs_compression_base64(b64_data: str, byte_size: int) -> bool:
    """Check if base64 image needs compression based on size or resolution."""
    if byte_size > _INLINE_COMPRESS_THRESHOLD:
        return True
    import base64
    import io

    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        raw_bytes = base64.b64decode(b64_data)
        with Image.open(io.BytesIO(raw_bytes)) as img:
            w, h = img.size
            return w > 4096 or h > 4096
    except Exception as e:
        logger.debug("Failed to check channel image resolution: %s", e)
        return False


def _compress_base64_image(b64_data: str) -> str | None:
    """Compress a base64-encoded image to JPEG with max 4096px dimension.

    Returns compressed base64 string or None if compression fails.
    """
    import base64
    import io

    try:
        from PIL import Image, ImageOps

        Image.MAX_IMAGE_PIXELS = None
        raw_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(img)
        w, h = img.size
        max_dim = 4096
        if w > max_dim or h > max_dim:
            ratio = min(max_dim / w, max_dim / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80, optimize=True)
        compressed = out.getvalue()
        logger.info(
            "Channel image compressed: %dKB -> %dKB",
            len(raw_bytes) // 1024,
            len(compressed) // 1024,
        )
        return base64.b64encode(compressed).decode("ascii")
    except Exception as e:
        logger.warning("Channel image compression failed: %s", e)
    return None


# =============================================================================
# Human Content Processing
# =============================================================================


async def _process_human_content(
    content: ContentItem,
    meta: dict[str, object] = None,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
) -> str | list[str | dict[str, object]]:
    """处理人类消息内容，支持文本和图片，使用 asyncio.gather 并发提升多图处理性能"""
    if meta is None:
        meta = {}
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        import asyncio

        tasks = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    tasks.append(_process_image_item(item, meta, model_cfg, vision_fallback_model_cfg))
                elif item.get("type") == "video_url":
                    tasks.append(_process_video_item(item, meta, model_cfg, vision_fallback_model_cfg))
                elif item.get("type") == "text":

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
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

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


async def _process_image_item(
    item: dict[str, object],
    meta: dict[str, object] = None,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
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
        url_raw = iu_dict.get("url", "")
        image_url = str(url_raw) if url_raw is not None else ""

        if not image_url:
            return item

        if not (is_image_url(image_url) or is_base64_data_url(image_url)):
            return item

        supports_vision = getattr(model_cfg, "supports_vision", False) if model_cfg else True

        # 计算图片哈希用于字典缓存隔离
        img_hash = hashlib.md5(image_url.encode("utf-8")).hexdigest()

        if not supports_vision and vision_fallback_model_cfg:
            extra_data = meta.get("extra_data", {}) if isinstance(meta.get("extra_data"), dict) else {}
            vision_cache = extra_data.get("vision_cache", {})
            if img_hash in vision_cache:
                return {"type": "text", "text": vision_cache[img_hash]}

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
                logger.warning("Converted image too large to read (%d bytes), degrading to text", byte_size)
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

        if not supports_vision and vision_fallback_model_cfg:
            from myrm_agent_harness.api import LLMConfig
            from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
                VisionFallbackEngine,
            )

            try:
                fallback_config = LLMConfig.model_validate(vision_fallback_model_cfg, from_attributes=True)
                engine = VisionFallbackEngine(fallback_config)

                # 标记该 meta 经历了图像分析，用于外部清除状态
                meta["_analyzed_image"] = True

                # Notify frontend that vision fallback is running
                chat_id = meta.get("chat_id")
                if chat_id:
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
                                        "status": "analyzing_image",
                                        "message": "Analyzing image with vision model...",
                                    },
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
                    extra_data["vision_cache"][img_hash] = fallback_text

                return {"type": "text", "text": fallback_text}
            except Exception as e:
                logger.warning(f"Vision fallback failed: {e}")
                return {
                    "type": "text",
                    "text": f"[Image Analysis Failed: {e}]",
                }

        return {"type": "image_url", "image_url": {"url": data_url}}

    except Exception as e:
        logger.warning(f"Error processing image item: {e}")
        return item


async def _process_video_item(
    item: dict[str, object],
    meta: dict[str, object] = None,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
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

        if not supports_video and vision_fallback_model_cfg:
            extra_data = meta.get("extra_data", {}) if isinstance(meta.get("extra_data"), dict) else {}
            video_cache = extra_data.get("video_cache", {})
            if video_hash in video_cache:
                return {"type": "text", "text": video_cache[video_hash]}

        if supports_video:
            mime = str(vu_dict.get("mime_type", "video/mp4"))
            return {
                "type": "image_url",
                "image_url": {"url": video_url, "detail": "auto"},
                "_mime_type": mime,
            }

        if vision_fallback_model_cfg:
            from myrm_agent_harness.api import LLMConfig
            from myrm_agent_harness.toolkits.llms.vision.video_analysis_engine import (
                VideoAnalysisEngine,
            )

            try:
                fallback_config = LLMConfig.model_validate(vision_fallback_model_cfg, from_attributes=True)
                engine = VideoAnalysisEngine(fallback_config)

                meta["_analyzed_video"] = True

                chat_id = meta.get("chat_id")
                if chat_id:
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
                                        "status": "analyzing_video",
                                        "message": "Analyzing video content...",
                                    },
                                },
                            },
                        )
                    )

                fallback_text = await engine.analyze_video_url(video_url)
                fallback_text = f"[Video Analysis]:\n{fallback_text}"

                message_id = meta.get("message_id")
                if message_id and isinstance(message_id, str):
                    if "video_cache" not in extra_data:
                        extra_data["video_cache"] = {}
                    extra_data["video_cache"][video_hash] = fallback_text

                return {"type": "text", "text": fallback_text}
            except Exception as e:
                logger.warning("Video analysis fallback failed: %s", e)
                return {
                    "type": "text",
                    "text": f"[Video Analysis Failed: {e}]",
                }

        return {
            "type": "text",
            "text": "[Video attached — current model does not support native video analysis. "
            "Configure a vision fallback model for video frame analysis.]",
        }

    except Exception as e:
        logger.warning("Error processing video item: %s", e)
        return item
