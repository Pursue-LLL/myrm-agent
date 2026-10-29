"""User-facing error payload for a request the concurrency gate refused.

[INPUT]
- app.services.agent.gateway::AgentQueueTimeout (POS: queue / drain / execution-timeout errors surfaced to the client)

[OUTPUT]
- queue_timeout_error_data: structured SSE error data (localized message, resolution steps, reason) for an AgentQueueTimeout

[POS]
Turns why a request was refused (memory pressure, per-user limit, global limit) and which sessions hold the slots into an actionable, localized message.
"""

from __future__ import annotations

import uuid

from app.services.agent.gateway import AgentQueueTimeout


def queue_timeout_error_data(
    exc: AgentQueueTimeout,
    message_id: str | None,
    locale: str | None,
) -> dict[str, object]:
    """Build a structured, user-facing error for AgentQueueTimeout.

    Distinguishes the three concurrency-limit causes and names the current
    holders so the message stays actionable.
    """
    lang = "zh" if (locale or "en").startswith("zh") else "en"
    holders = exc.active_sessions
    holder_summary = ""
    if holders:
        names = [f"{h.get('chatId', h.get('agentType', 'session'))} ({h.get('agentType', 'agent')})" for h in holders[:3]]
        if len(holders) > 3:
            extra = len(holders) - 3
            names.append(f"等 {extra} 个会话" if lang == "zh" else f"+{extra} more")
        holder_summary = f" 当前占用：{'、'.join(names)}。" if lang == "zh" else f" Held by: {', '.join(names)}."

    if exc.reason == "memory_pressure":
        user_message = (
            "服务内存压力过高，已暂停接收新任务，请稍后重试。"
            if lang == "zh"
            else "Server memory pressure is high and new tasks are paused. Please retry shortly."
        )
        resolution_steps = (
            ["等待内存压力缓解后重试", "若持续出现，请关闭其他占用内存的程序"]
            if lang == "zh"
            else [
                "Wait for memory pressure to ease and retry",
                "If it persists, close other memory-heavy programs",
            ]
        )
    elif exc.reason == "user_limit":
        user_message = (
            f"并发会话已达上限，无法接收新请求。{holder_summary}请先结束部分运行中的任务后重试。"
            if lang == "zh"
            else (
                f"Concurrency limit reached; the request could not be accepted."
                f"{holder_summary} Please finish or stop some running tasks and retry."
            )
        )
        resolution_steps = (
            ["前往工作台查看并结束运行中的会话", "等待已有任务完成后重试"]
            if lang == "zh"
            else [
                "Open the workspace and stop running sessions",
                "Wait for an active task to finish and retry",
            ]
        )
    else:
        user_message = (
            f"服务繁忙，无法接收新请求。{holder_summary}请稍后重试。"
            if lang == "zh"
            else f"Server is busy; the request could not be accepted.{holder_summary} Please retry shortly."
        )
        resolution_steps = (
            ["稍后重试", "若持续出现，请检查是否有较多并发任务"]
            if lang == "zh"
            else [
                "Retry shortly",
                "If it persists, check whether too many tasks are running",
            ]
        )

    return {
        "type": "error",
        "error_kind": "concurrency_limit",
        "data": user_message,
        "messageId": message_id or str(uuid.uuid4()),
        "diagnostic_result": {
            "error_type": "concurrency_limit",
            "user_message": user_message,
            "resolution_steps": resolution_steps,
            "locale": lang,
        },
        "metadata": {
            "error_type": "concurrency_limit",
            "reason": exc.reason,
        },
    }
