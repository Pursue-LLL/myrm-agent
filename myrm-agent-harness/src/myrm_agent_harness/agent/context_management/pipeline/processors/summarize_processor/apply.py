"""[INPUT]
- agent.context_management.pipeline.base::ProcessorContext (POS: 处理器上下文)
- agent.context_management.infra.schemas::StructuredSummary (POS: 结构化摘要类型)
- agent.context_management.strategies.compactor.pre_compact_context::prepend_pre_compact_message (POS: 预压缩消息拼接)
- agent.context_management.strategies.summary.summary_builder (POS: 受保护头部与近期消息提取)
- utils.token_estimation::estimate_messages_tokens (POS: token 估算)

[OUTPUT]
- assemble_summarized_messages: 用摘要替换历史消息并返回替换后的 token 数

[POS]
`summarize_processor/` 的消息重写步骤：受保护头部 + 摘要 + 近期尾部，LLM 与降级路径共用。
"""

from __future__ import annotations

from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

from ....infra.schemas import ContextConfig, StructuredSummary
from ....strategies.compactor.pre_compact_context import prepend_pre_compact_message
from ....strategies.summary.summary_builder import (
    create_summary_message,
    extract_protected_head,
    extract_recent_messages,
)
from ...base import ProcessorContext


def assemble_summarized_messages(
    context: ProcessorContext,
    summary: StructuredSummary,
    config: ContextConfig,
) -> int:
    """Rewrite ``context.messages`` as protected head + summary + recent tail.

    Returns the token count of the rewritten list so the caller can report savings.
    """
    protected_head = extract_protected_head(context.messages)
    tail_budget = int((config.max_context_tokens or 128000) * getattr(config, "tail_budget_ratio", 0.20))
    recent_messages = extract_recent_messages(context.messages, tail_budget)
    protected_ids = {id(m) for m in protected_head}
    recent_messages = [m for m in recent_messages if id(m) not in protected_ids]
    summary_message = create_summary_message(summary, context.chat_id)

    context.messages = prepend_pre_compact_message(
        protected_head,
        [summary_message],
        recent_messages,
        context=context,
    )

    from ....infra.cache_break_detector import get_cache_break_detector

    detector = get_cache_break_detector()
    if detector is not None:
        detector.notify_compaction()

    return estimate_messages_tokens(context.messages)
