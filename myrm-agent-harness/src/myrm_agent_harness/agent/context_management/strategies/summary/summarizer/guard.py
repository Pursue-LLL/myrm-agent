"""[INPUT]
- myrm_agent_harness.toolkits.llms.utils.model_utils::get_model_context_limit (POS: Stateless utilities for inspecting LLM model properties.)
- myrm_agent_harness.utils.logger_utils::get_agent_logger (POS: Unified logging utilities. Provides consistent log format and convenience methods)
- myrm_agent_harness.utils.token_estimation::estimate_context_tokens / estimate_messages_tokens (POS: Token estimation infrastructure. Covers message-level tokens and bind-tools overhead for)
- myrm_agent_harness.agent.context_management.infra.schemas::ContextConfig (POS: Context management shared data structures. Defines compact format types, summary schemas, and configuration constants as)

[OUTPUT]
- _guard_aux_context: Trim messages to fit within the aux model's context window.
- should_summarize: Check whether proactive summarization should be triggered (dual-signal).

[POS]
摘要策略子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

from myrm_agent_harness.toolkits.llms.utils.model_utils import get_model_context_limit
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import (
    estimate_context_tokens,
    estimate_messages_tokens,
)

from ....infra.schemas import ContextConfig

logger = get_agent_logger(__name__)

_AUX_CONTEXT_SAFETY_RATIO = 0.8
_AUX_PROMPT_OVERHEAD = 2000


def _guard_aux_context(
    messages: list[BaseMessage],
    llm: BaseChatModel,
    prompt_tokens: int = _AUX_PROMPT_OVERHEAD,
) -> list[BaseMessage]:
    """Trim messages to fit within the aux model's context window.

    When the summarizer LLM has a smaller context window than the main model,
    the full message history may exceed its capacity, causing a hard
    ``context_length_exceeded`` error. This guard trims from the head (keeping
    the most recent messages) so the LLM call stays within safe bounds.

    Returns the original list unchanged when no trimming is needed or when the
    model's context limit cannot be determined (graceful no-op).
    """
    aux_limit = get_model_context_limit(llm)
    if aux_limit is None:
        return messages

    safe_budget = int(aux_limit * _AUX_CONTEXT_SAFETY_RATIO) - prompt_tokens
    if safe_budget <= 0:
        logger.warning(
            "[Summarize] Aux model context too small to hold even the prompt "
            "(limit=%d, prompt_overhead=%d) — skipping guard",
            aux_limit,
            prompt_tokens,
        )
        return messages

    total_tokens = estimate_messages_tokens(messages)
    if total_tokens <= safe_budget:
        return messages

    trimmed: list[BaseMessage] = []
    running = 0
    for msg in reversed(messages):
        msg_tokens = estimate_messages_tokens([msg])
        if running + msg_tokens > safe_budget:
            break
        trimmed.insert(0, msg)
        running += msg_tokens

    if not trimmed:
        trimmed = messages[-1:]

    logger.warning(
        "[Summarize] Aux context guard: trimmed %d → %d messages (aux_limit=%d, safe_budget=%d, original_tokens=%d)",
        len(messages),
        len(trimmed),
        aux_limit,
        safe_budget,
        total_tokens,
    )
    return trimmed


def should_summarize(
    messages: list[BaseMessage],
    config: ContextConfig | None = None,
    ignore_api_tokens: bool = False,
    *,
    bound_tool_overhead_tokens: int = 0,
    last_provider_prompt_tokens: int | None = None,
) -> bool:
    """Check whether proactive summarization should be triggered (dual-signal)."""
    from ....infra.schemas import DEFAULT_CONTEXT_CONFIG

    cfg = config or DEFAULT_CONTEXT_CONFIG
    total_tokens = estimate_context_tokens(
        messages,
        bound_tool_overhead_tokens=bound_tool_overhead_tokens,
        last_provider_prompt_tokens=last_provider_prompt_tokens,
    )
    max_window = cfg.max_context_tokens or 120000
    threshold = cfg.proactive_reset_threshold

    if total_tokens >= threshold:
        ratio = total_tokens / max_window
        logger.warning(
            f" [Summarize] proactive_reset triggered: "
            f"tokens={total_tokens}, threshold={threshold}, "
            f"max_window={max_window}, ratio={ratio:.1%}"
        )
        return True

    passive_threshold = cfg.summarize_trigger_threshold
    if total_tokens >= passive_threshold:
        ratio = total_tokens / max_window
        logger.warning(
            f" [Summarize] passive threshold triggered: "
            f"tokens={total_tokens}, threshold={passive_threshold}, "
            f"max_window={max_window}, ratio={ratio:.1%}"
        )
        return True

    if ignore_api_tokens:
        return False

    api_input_tokens = 0
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            usage = getattr(msg, "usage_metadata", None)
            if usage and isinstance(usage, dict):
                api_input_tokens = usage.get("input_tokens", 0)

            if api_input_tokens == 0:
                resp_meta = getattr(msg, "response_metadata", {})
                if isinstance(resp_meta, dict):
                    token_usage = resp_meta.get("token_usage", {})
                    if isinstance(token_usage, dict):
                        api_input_tokens = token_usage.get("prompt_tokens", 0)

            break

    if api_input_tokens >= threshold:
        ratio = api_input_tokens / max_window
        logger.warning(
            f" [Summarize] API token signal triggered: "
            f"local_estimate={total_tokens}, api_input={api_input_tokens}, "
            f"threshold={threshold}, max_window={max_window}, ratio={ratio:.1%}"
        )
        return True

    logger.debug(
        f" [Summarize Check] total={total_tokens}, api_input={api_input_tokens}, "
        f"threshold={threshold}, max_window={max_window}"
    )
    return False
