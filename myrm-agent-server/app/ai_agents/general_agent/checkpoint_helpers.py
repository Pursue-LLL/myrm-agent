"""Browser checkpoint lifecycle helpers for GeneralAgent.

[INPUT]
- myrm_agent_harness.toolkits.browser.checkpoint::BrowserCheckpointHelper, ThreadStore
- app.platform_utils::get_checkpointer

[OUTPUT]
- update_checkpoint_counters: 根据工具调用事件更新 checkpoint 计数器
- mark_thread_completed: 标记线程为已完成状态
- mark_thread_failed: 标记线程为失败状态

[POS]
GeneralAgent 的 checkpoint 生命周期辅助函数。处理浏览器工具事件计数、
线程状态标记等 checkpoint 相关逻辑。
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.checkpoint import BrowserCheckpointHelper

logger = logging.getLogger(__name__)


async def update_checkpoint_counters(
    checkpoint_helper: "BrowserCheckpointHelper | None",
    event: dict[str, Any],
) -> bool:
    """根据工具调用事件更新 checkpoint 计数器

    Args:
        checkpoint_helper: BrowserCheckpointHelper 实例
        event: Agent 事件（包含 type 和 data）

    Returns:
        True if this was a browser tool event (context should be updated)
    """
    if not checkpoint_helper:
        return False

    event_type = event.get("type")
    if event_type not in ("tool_call", "tasks_steps"):
        return False

    event_data = event.get("data", {})
    if isinstance(event_data, list):
        # Handle case where data is a list of tool calls
        if len(event_data) > 0 and isinstance(event_data[0], dict):
            tool_name = event_data[0].get("tool_name", "")
        else:
            tool_name = ""
    else:
        tool_name = event_data.get("tool_name", "")
    if not tool_name:
        return False

    is_browser_tool = any(
        keyword in tool_name.lower() for keyword in ["browser", "snapshot", "inspect", "interact", "navigate", "tab"]
    )

    if not is_browser_tool:
        return False

    if "snapshot" in tool_name or "inspect" in tool_name:
        checkpoint_helper.increment_counter("snapshots")
    elif "interact" in tool_name or "click" in tool_name or "type" in tool_name:
        checkpoint_helper.increment_counter("interactions")
    elif "navigate" in tool_name or "new_tab" in tool_name:
        checkpoint_helper.increment_counter("navigations")

    return True


async def mark_thread_completed(thread_id: str | None) -> None:
    """标记线程为已完成状态

    Args:
        thread_id: 线程 ID
    """
    if not thread_id:
        return

    try:
        from myrm_agent_harness.toolkits.browser.checkpoint import ThreadStore

        from app.platform_utils import get_checkpointer

        checkpointer = get_checkpointer()

        if hasattr(checkpointer, "thread_store"):
            thread_store: ThreadStore = checkpointer.thread_store
            await thread_store.mark_completed(thread_id)
            logger.info(f"Checkpoint: marked thread {thread_id} as completed")
    except Exception as exc:
        logger.warning(f"Failed to mark thread completed: {exc}")


async def mark_thread_failed(thread_id: str | None) -> None:
    """标记线程为失败状态

    Args:
        thread_id: 线程 ID
    """
    if not thread_id:
        return

    try:
        from myrm_agent_harness.toolkits.browser.checkpoint import ThreadStore

        from app.platform_utils import get_checkpointer

        checkpointer = get_checkpointer()

        if hasattr(checkpointer, "thread_store"):
            thread_store: ThreadStore = checkpointer.thread_store
            await thread_store.mark_failed(thread_id)
            logger.info(f"Checkpoint: marked thread {thread_id} as failed")
    except Exception as exc:
        logger.warning(f"Failed to mark thread failed: {exc}")
