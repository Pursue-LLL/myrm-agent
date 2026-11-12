"""Smart fallback strategy for extreme token overflow scenarios.

When essential content (CRITICAL + HIGH priority) alone exceeds budget,
this module provides a fallback strategy to gracefully degrade compression.

Fallback策略（当HIGH-priority内容超预算）：
1. 保留所有Priority 0-1 (human messages / 最后一轮内容) 完整
2. 工具调用组 (AIMessage 调用 + ToolMessage 结果,不论成败) 均分剩余预算,调用与结果各按份额截断;
   从最新的组往最旧的组装入,预算耗尽就丢弃更旧的组
3. 一行摘要Priority 3 (reasoning),同样先新后旧
4. 按原始对话顺序输出,再由 ensure_tool_pair_integrity 清掉孤儿 ToolMessage、去掉没有结果的 tool_call,
   防止不完整的工具调用对传递给 LLM

[INPUT]
- (none)

[OUTPUT]
- apply_smart_fallback: Apply smart fallback when essential content exceeds budget.

[POS]
Smart fallback strategy for extreme token overflow scenarios.
"""

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

from ...infra.message_priority import MessagePriority, classify_message_priority, last_iteration_flags
from ..compression.compression_formatting import shrink_tool_call_args
from ..tool_call_groups import build_tool_call_groups
from .integrity_guard import ensure_tool_pair_integrity

logger = get_agent_logger(__name__)


async def apply_smart_fallback(
    messages: list[BaseMessage],
    max_tokens: int,
    *,
    failed_tool_call_ids: frozenset[str] | None = None,
) -> tuple[list[BaseMessage], int]:
    """Apply smart fallback when essential content exceeds budget.

    Args:
        messages: Original messages
        max_tokens: Maximum allowed tokens

    Returns:
        (Fallback messages, tokens saved)
    """
    logger.warning(f" Applying SMART FALLBACK: essential content exceeds {max_tokens} tokens")

    protected_tool_calls = failed_tool_call_ids or frozenset()

    # Detect last iteration
    is_last_iteration = last_iteration_flags(messages)

    # Phase 1: Keep all CRITICAL (priority 0-1) messages
    critical_messages: list[tuple[int, BaseMessage]] = []
    for i, msg in enumerate(messages):
        priority = classify_message_priority(
            msg,
            is_last_iteration=is_last_iteration.get(id(msg), False),
            failed_tool_call_ids=protected_tool_calls,
        )
        if priority <= MessagePriority.CRITICAL_FINAL:
            critical_messages.append((i, msg))

    # Every kept message carries its original index so the result can be put back in conversation order.
    kept: list[tuple[int, BaseMessage]] = list(critical_messages)
    used_tokens = estimate_messages_tokens([msg for _, msg in kept])

    if used_tokens >= max_tokens:
        logger.error(f" Even CRITICAL messages exceed budget ({used_tokens} >= {max_tokens})")
        return [msg for _, msg in kept], 0

    remaining_budget = max_tokens - used_tokens

    # Phase 2: Budget-allocate HIGH priority tool pairs atomically
    high_group_indices: set[int] = set()
    high_groups = []
    for group in build_tool_call_groups(messages):
        ai_priority = classify_message_priority(
            group.ai_message,
            is_last_iteration=is_last_iteration.get(id(group.ai_message), False),
            failed_tool_call_ids=protected_tool_calls,
        )
        tool_priority = classify_message_priority(
            group.tool_message,
            is_last_iteration=is_last_iteration.get(id(group.tool_message), False),
            failed_tool_call_ids=protected_tool_calls,
        )
        if ai_priority in {MessagePriority.HIGH_TOOL_CALL, MessagePriority.HIGH_TOOL_ERROR} or tool_priority in {
            MessagePriority.HIGH_TOOL_CALL,
            MessagePriority.HIGH_TOOL_ERROR,
        }:
            high_groups.append(group)
            high_group_indices.update({group.ai_index, group.tool_index})

    if high_groups:
        per_group_budget = max(320, remaining_budget // (len(high_groups) + 1))
        # Newest first: when the budget runs out it is the oldest groups that go.
        for group in reversed(high_groups):
            ai_budget = max(120, per_group_budget // 3)
            tool_budget = max(200, per_group_budget - ai_budget)

            ai_message: BaseMessage = group.ai_message
            tool_message: BaseMessage = group.tool_message

            if estimate_messages_tokens([group.ai_message]) > ai_budget:
                ai_message = _truncate_ai_message(group.ai_message, ai_budget)
            if estimate_messages_tokens([group.tool_message]) > tool_budget:
                tool_message = _truncate_tool_message(group.tool_message, tool_budget)

            pair_tokens = estimate_messages_tokens([ai_message, tool_message])
            if used_tokens + pair_tokens > max_tokens:
                break

            kept.extend([(group.ai_index, ai_message), (group.tool_index, tool_message)])
            used_tokens += pair_tokens

    # Phase 3: One-line summaries for MEDIUM priority (reasoning)
    if used_tokens < max_tokens:
        medium_messages: list[tuple[int, BaseMessage]] = []
        for i, msg in enumerate(messages):
            if i in {idx for idx, _ in critical_messages} or i in high_group_indices:
                continue
            priority = classify_message_priority(
                msg,
                is_last_iteration=is_last_iteration.get(id(msg), False),
                failed_tool_call_ids=protected_tool_calls,
            )
            if priority == MessagePriority.MEDIUM_REASONING:
                medium_messages.append((i, msg))

        for idx, msg in reversed(medium_messages):
            if isinstance(msg, AIMessage) and msg.content:
                # One-line summary (first 100 chars)
                summary = str(msg.content).split("\n")[0][:100]
                summary_msg = AIMessage(content=f"[Summarized] {summary}...")
                kept.append((idx, summary_msg))
                used_tokens += estimate_messages_tokens([summary_msg])
                if used_tokens >= max_tokens:
                    break

    # Tool Integrity Guard: Ensure semantic completeness of tool call pairs
    # This prevents sending incomplete tool call sequences to the LLM
    result_messages = ensure_tool_pair_integrity([msg for _, msg in sorted(kept, key=lambda item: item[0])])

    # Calculate tokens saved
    original_tokens = estimate_messages_tokens(messages)
    tokens_saved = original_tokens - estimate_messages_tokens(result_messages)

    logger.warning(
        f" Smart fallback applied: kept {len(result_messages)}/{len(messages)} messages, saved {tokens_saved} tokens"
    )

    return result_messages, tokens_saved


def _truncate_tool_message(msg: ToolMessage, budget_tokens: int) -> ToolMessage:
    """Truncate tool message to fit budget."""
    content = str(msg.content)
    # Estimate ~4 chars per token
    max_chars = budget_tokens * 4
    if len(content) > max_chars:
        content = content[:max_chars] + f"... [budget-truncated, total {len(content)} chars]"

    return ToolMessage(content=content, tool_call_id=msg.tool_call_id)


def _truncate_ai_message(msg: AIMessage, budget_tokens: int) -> AIMessage:
    """Truncate AI message to fit budget.

    Shrinks both text content AND tool_call args to prevent oversized
    JSON arguments from causing API 400 errors after truncation.
    """
    content = str(msg.content) if msg.content else ""
    max_chars = budget_tokens * 4
    if len(content) > max_chars:
        content = content[:max_chars] + "... [budget-truncated]"

    tool_calls = shrink_tool_call_args(msg.tool_calls) if msg.tool_calls else msg.tool_calls

    return AIMessage(content=content, tool_calls=tool_calls)
