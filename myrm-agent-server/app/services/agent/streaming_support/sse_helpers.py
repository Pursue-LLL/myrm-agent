"""SSE event parsing and formatting.

[INPUT]
- app.schemas.streaming::SSEEnvelope (POS: SSE 事件封装)

[OUTPUT]
- error_sse: 构造错误 SSE 事件字符串
- is_compression_exhausted: 检测上下文压缩耗尽事件
- extract_approval_timeout: 提取审批超时信息
- extract_clarification_required: 检测 structured clarify interrupt SSE
- extract_directory_request_required: 检测 request_directory interrupt SSE
- clear_context_task_metrics: 清理 harness 侧 TaskMetrics

[POS]
SSE 事件辅助层。提供 SSE 事件解析与错误格式化，供 stream_loop / stream_finalize / hitl_timeout 调用。
"""

from __future__ import annotations

import logging
import uuid

import orjson

from app.schemas.streaming import SSEEnvelope

logger = logging.getLogger(__name__)

_SSE_DATA_PREFIX = "data: "


def error_sse(message: str, message_id: str | None) -> str:
    data: dict[str, object] = {
        "type": "error",
        "data": message,
        "messageId": message_id or str(uuid.uuid4()),
    }
    return SSEEnvelope.from_any(data).to_sse_chunk()


def clear_context_task_metrics(chat_id: str | None) -> None:
    """Clear harness-side TaskMetrics after a request completes."""
    if not chat_id:
        return
    try:
        from myrm_agent_harness.agent.context_management.tracking.task_metrics import clear_task_metrics

        clear_task_metrics(chat_id)
    except Exception as exc:
        logger.warning("Failed to clear context task metrics for chat %s: %s", chat_id, exc)


def is_compression_exhausted(sse_chunk: str) -> bool:
    """Check if an SSE chunk signals context compression exhaustion."""
    if "compression_exhausted" not in sse_chunk:
        return False
    if not sse_chunk.startswith(_SSE_DATA_PREFIX):
        return False
    try:
        event = orjson.loads(sse_chunk[len(_SSE_DATA_PREFIX) :].rstrip())
        return event.get("type") == "error" and event.get("compression_exhausted") is True
    except (orjson.JSONDecodeError, TypeError):
        return False


def extract_approval_timeout(sse_chunk: str) -> dict[str, object] | None:
    """Extract timeout info from a TOOL_APPROVAL_REQUEST SSE event."""
    if "tool_approval_request" not in sse_chunk:
        return None
    if not sse_chunk.startswith(_SSE_DATA_PREFIX):
        return None
    try:
        event = orjson.loads(sse_chunk[len(_SSE_DATA_PREFIX) :].rstrip())
        if event.get("type") != "tool_approval_request":
            return None
        data = event.get("data")
        if not isinstance(data, dict):
            return None
        extensions = data.get("extensions", {})
        if not isinstance(extensions, dict):
            return None
        timeout = extensions.get("timeout", {})
        if not isinstance(timeout, dict):
            return None
        return {
            "seconds": timeout.get("seconds", 300),
            "behavior": timeout.get("behavior", "deny"),
        }
    except (orjson.JSONDecodeError, TypeError):
        return None


def extract_clarification_required(sse_chunk: str) -> bool:
    """Return True when an SSE chunk signals a structured clarification interrupt."""
    if "clarification_required" not in sse_chunk:
        return False
    if not sse_chunk.startswith(_SSE_DATA_PREFIX):
        return False
    try:
        event = orjson.loads(sse_chunk[len(_SSE_DATA_PREFIX) :].rstrip())
        return bool(event.get("type") == "clarification_required")
    except (orjson.JSONDecodeError, TypeError):
        return False


def extract_directory_request_required(sse_chunk: str) -> bool:
    """Return True when an SSE chunk signals a request_directory interrupt."""
    if "directory_request_required" not in sse_chunk:
        return False
    if not sse_chunk.startswith(_SSE_DATA_PREFIX):
        return False
    try:
        event = orjson.loads(sse_chunk[len(_SSE_DATA_PREFIX) :].rstrip())
        return bool(event.get("type") == "directory_request_required")
    except (orjson.JSONDecodeError, TypeError):
        return False
