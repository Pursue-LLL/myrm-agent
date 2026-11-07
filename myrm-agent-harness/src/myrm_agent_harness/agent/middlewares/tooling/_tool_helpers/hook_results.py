"""[INPUT]
- .truncation::smart_truncate_output (POS: 文本截断)
- agent.security.audit::record_decision (POS: 安全审计)
- agent.errors.tool_error_category::ToolErrorCategory (POS: 工具错误分类)
- utils.logger_utils::get_agent_logger (POS: 统一日志器)
- langchain_core.messages::ToolMessage (POS: 消息类型)

[OUTPUT]
- build_hook_failure_result: 把 hook 失败转成错误 ToolMessage
- emit_hook_failure_event / emit_archive_restore_block_status: 可观测性事件

[POS]
`_tool_helpers/` 的 hook 结果与事件发射；不参与核心安全判定。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.errors.tool_error_category import ToolErrorCategory
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from .truncation import smart_truncate_output

logger = get_agent_logger(__name__)

def build_hook_failure_result(
    result: ToolMessage,
    post_hook_result: Any,
    tool_name: str,
    tool_call_id: str,
    post_result_text: str,
) -> ToolMessage:
    """Build error ToolMessage from hook validation failure."""
    error_details = []
    for hook_result in post_hook_result.results:
        if hook_result.blocked or not hook_result.success:
            if hook_result.output:
                error_details.append(hook_result.output)
            elif hook_result.reason:
                error_details.append(hook_result.reason)

    hook_error_msg = "\n".join(error_details) if error_details else "Hook validation failed"
    truncated_output = smart_truncate_output(post_result_text, max_lines=20)
    error_content = (
        f"[HOOK_VALIDATION_FAILED] Post-execution hook detected critical issues:\n\n"
        f"{hook_error_msg}\n\n"
        f"Original tool output:\n{truncated_output}"
    )

    record_decision(tool_name, "POST_HOOK_BLOCKED", post_hook_result.reason)
    logger.warning("POST_TOOL_USE hook blocked: %s -- %s", tool_name, post_hook_result.reason)

    return ToolMessage(
        content=error_content,
        name=tool_name,
        tool_call_id=result.tool_call_id,
        status="error",
        additional_kwargs={"error_category": ToolErrorCategory.POST_HOOK_BLOCKED},
    )

async def emit_hook_failure_event(tool_name: str, post_hook_result: Any, agent_event_type: Any) -> None:
    """Emit observability events for hook failures."""
    try:
        from myrm_agent_harness.observability.metrics.registry import (
            metrics_registry,
        )

        if metrics_registry and metrics_registry.enabled:
            metrics_registry.record_hook_failure(agent_id="base_agent", tool_name=tool_name, hook_event="post_tool_use")
    except ImportError:
        pass

    try:
        from myrm_agent_harness.utils.runtime.progress_sink import (
            get_tool_progress_sink,
        )

        sink = get_tool_progress_sink()
        if sink:
            await sink.emit(
                {
                    "type": agent_event_type.TOOL_FAILURE.value,
                    "data": {
                        "tool_name": tool_name,
                        "hook_event": "post_tool_use",
                        "error": post_hook_result.reason or "Hook validation failed",
                        "reason": post_hook_result.reason,
                        "blocked": post_hook_result.blocked,
                    },
                }
            )
    except (ImportError, AttributeError):
        pass

async def emit_archive_restore_block_status(result_text: str, tool_name: str) -> None:
    """Emit status event when archive restore is blocked."""
    from myrm_agent_harness.agent.meta_tools.file_ops.core.archive_restore_guard import (
        parse_archive_restore_block_payload,
    )

    payload = parse_archive_restore_block_payload(result_text)
    if payload is None:
        return

    suggested_action = payload.get("suggested_action")
    items: list[dict[str, str]] = []
    if isinstance(suggested_action, str) and suggested_action:
        items.append({"text": suggested_action})

    try:
        from myrm_agent_harness.utils.event_utils import dispatch_custom_event

        await dispatch_custom_event(
            "agent_status",
            {
                "step_key": "archive_restore_blocked",
                "tool_name": tool_name,
                "status": "warning",
                "items": items,
                "archive_restore_block": payload,
            },
        )
    except Exception as exc:
        logger.debug("Failed to emit archive restore block status: %s", exc)
