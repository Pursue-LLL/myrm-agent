"""SSE event parsing, formatting, and approval timeout scheduling.

[INPUT]
- myrm_agent_harness.agent.streaming.types::ApprovalInterceptedEventData (POS: 审批拦截事件数据)
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: 审批超时调度器)
- app.schemas.streaming::SSEEnvelope (POS: SSE 事件封装)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: 流内容收集器)

[OUTPUT]
- error_sse: 构造错误 SSE 事件字符串
- is_compression_exhausted: 检测上下文压缩耗尽事件
- extract_approval_intercepted: 提取审批拦截信息
- extract_approval_timeout: 提取审批超时信息
- schedule_approval_timeout: 注册审批超时后台守护
- clear_context_task_metrics: 清理 harness 侧 TaskMetrics

[POS]
SSE 事件辅助层。提供 SSE 事件解析、错误格式化和审批超时调度能力，
供 streaming.py 主路由调用。
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import orjson
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.types import ApprovalInterceptedEventData

from app.schemas.streaming import SSEEnvelope
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

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


def extract_approval_intercepted(sse_chunk: str) -> ApprovalInterceptedEventData | None:
    """Extract approval_intercepted info from an APPROVAL_INTERCEPTED SSE event."""
    if "approval_intercepted" not in sse_chunk:
        return None
    if not sse_chunk.startswith(_SSE_DATA_PREFIX):
        return None
    try:
        event = orjson.loads(sse_chunk[len(_SSE_DATA_PREFIX) :].rstrip())
        if event.get("type") != "approval_intercepted":
            return None
        data = event.get("data")
        if not isinstance(data, dict):
            return None
        return ApprovalInterceptedEventData(**data)
    except Exception:
        return None


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


def schedule_approval_timeout(
    chat_id: str,
    timeout_info: dict[str, object],
    params: GeneralAgentParams,
) -> None:
    """Register a backend timeout guard for a pending approval request."""
    raw_seconds = timeout_info.get("seconds", 300)
    if isinstance(raw_seconds, (int, float)):
        timeout_seconds = float(raw_seconds)
    elif isinstance(raw_seconds, str):
        timeout_seconds = float(raw_seconds)
    else:
        timeout_seconds = 300.0
    behavior = str(timeout_info.get("behavior", "deny"))

    async def resume_callback(resume_value: dict[str, object]) -> None:
        from langgraph.types import Command

        from app.services.agent.streaming import ai_agent_service_stream
        from app.services.chat.chat_service import ChatService

        resume_params = params.model_copy()
        resume_params.query = Command(resume=resume_value)

        resume_collector = StreamContentCollector()
        next_approval_timeout: dict[str, object] | None = None
        async for chunk in ai_agent_service_stream(params=resume_params):
            sse_line = f"data: {orjson.dumps(chunk).decode('utf-8')}\n\n" if isinstance(chunk, dict) else str(chunk)
            resume_collector.feed_sse(sse_line)
            next_approval_timeout = extract_approval_timeout(sse_line) or next_approval_timeout

        if resume_collector.has_content:
            await ChatService.persist_assistant_message_safe(
                chat_id, resume_collector.content, extra_data=resume_collector.extra_data
            )

        if next_approval_timeout:
            schedule_approval_timeout(chat_id, next_approval_timeout, resume_params)
        else:
            logger.info("Backend timeout auto-resume completed: chat_id=%s", chat_id)

    ApprovalTimeoutScheduler.get().schedule(
        key=chat_id,
        timeout_seconds=timeout_seconds,
        behavior=behavior,
        resume_callback=resume_callback,
    )
