"""通用Agent的工具约束中间件

实现分层约束策略：
- 工具列表 100% 静态（保护 Prompt Cache）
- 通过 tool_choice 参数实现硬约束（L2 约束）
- 配合 Prompt 层 tool description 的软约束（L1 约束）

连续调用收敛机制：
- 当 request_answer_user_tool 被连续调用超过阈值时，恢复 tool_choice="auto"
  让模型回归自由选择模式去收集更多信息，打破"想回答但信息不足"的循环。

参考：myrm_agent_harness/agent/context_management/CONTEXT_ENGINEERING.md - 分层约束策略
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)

_ANSWER_TOOL_NAME = "request_answer_user_tool"
_MAX_CONSECUTIVE_ANSWER_CALLS = 2

_answer_consecutive_count: ContextVar[int] = ContextVar("answer_tool_consecutive_count", default=0)


def _count_trailing_answer_tool_messages(messages: list[object]) -> int:
    """Count consecutive request_answer_user_tool ToolMessages at the tail."""
    count = 0
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == _ANSWER_TOOL_NAME:
            count += 1
        else:
            break
    return count


def reset_answer_tool_convergence() -> None:
    """Reset convergence state. Call at the start of each agent run."""
    _answer_consecutive_count.set(0)


class ToolSelectionMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """工具约束中间件 - 通过 tool_choice 实现状态机约束

    分层约束策略（L2 层）：
    - 工具列表始终保持不变（保护 Prompt Cache）
    - 在 request_answer_user_tool 调用后，设置 tool_choice="none" 强制模型直接回答
    - 连续调用超过阈值后，恢复 tool_choice="auto" 打破循环

    状态机流程：
    1. 信息收集阶段：tool_choice="auto"（默认，模型自由选择工具）
    2. 调用 request_answer_user_tool 后（1-2次）：tool_choice="none"（强制回答）
    3. 连续调用 ≥3次：恢复 tool_choice="auto"（收敛保护，回归信息收集）
    """

    name = "tool_selection_middleware"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        raise NotImplementedError("ToolSelectionMiddleware does not support synchronous wrap_model_call")

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        state = request.state
        raw_messages = state.get("messages", [])
        messages: list[object] = raw_messages if isinstance(raw_messages, list) else []

        trailing_count = _count_trailing_answer_tool_messages(messages)

        if trailing_count > 0:
            consecutive = _answer_consecutive_count.get() + trailing_count
            _answer_consecutive_count.set(consecutive)

            if consecutive <= _MAX_CONSECUTIVE_ANSWER_CALLS:
                request = request.override(tool_choice="none")
                logger.info(
                    "ToolSelectionMiddleware: tool_choice='none' after request_answer_user_tool (consecutive=%d/%d)",
                    consecutive,
                    _MAX_CONSECUTIVE_ANSWER_CALLS,
                )
            else:
                logger.warning(
                    "ToolSelectionMiddleware: convergence triggered — restoring tool_choice='auto' "
                    "after %d consecutive request_answer_user_tool calls. "
                    "Model should collect more information instead of retrying answer.",
                    consecutive,
                )
        else:
            if _answer_consecutive_count.get() > 0:
                _answer_consecutive_count.set(0)
            logger.debug(
                "ToolSelectionMiddleware: tool_choice=%s, tools=%d",
                request.tool_choice,
                len(request.tools),
            )

        return await handler(request)


tool_selection_middleware = ToolSelectionMiddleware()
