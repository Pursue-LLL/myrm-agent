"""Context budget snapshots and the GUI breakdown.

[INPUT]
- langchain_core.messages::BaseMessage
- myrm_agent_harness.agent.streaming.types::ContextBudgetSnapshot
- myrm_agent_harness.agent.types::AgentRunStatistics

[OUTPUT]
- compute_context_budget_snapshot: lightweight budget snapshot from provider usage
- resolve_context_budget_breakdown: GUI six-category breakdown from the checkpoint

[POS]
Read-only context accounting shared by the runtime and the GUI. It is separate from the
run lifecycle so the token math (and its tests) do not depend on workspace setup.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from myrm_agent_harness.agent.streaming.types import ContextBudgetSnapshot
from myrm_agent_harness.agent.types import AgentRunStatistics


def compute_context_budget_snapshot(
    stats: AgentRunStatistics,
    max_context_tokens: int | None,
    *,
    messages_estimated_tokens: int | None = None,
    bound_tools_overhead_tokens: int | None = None,
    other_tokens: int | None = None,
    turn_count: int | None = None,
    system_prompt_tokens: int | None = None,
    memory_tokens: int | None = None,
    workspace_rules_tokens: int | None = None,
    mcp_tools_tokens: int | None = None,
    skills_tools_tokens: int | None = None,
    builtin_tools_tokens: int | None = None,
) -> ContextBudgetSnapshot | None:
    """Compute a lightweight context budget snapshot from token tracker stats.

    Uses actual prompt_tokens from the LLM provider (provider-reported,
    more accurate than character-based estimation).

    usage_percent is relative to max_context_tokens (user-facing percentage).
    health_status: healthy (<80%), warning (80-90%), critical (>=90%).

    Optional breakdown fields are GUI-only estimates; they do not affect pipeline
    compress/summarize decisions. ``turn_count`` mirrors the runtime
    compress_processor human-message count so the GUI preflight can reuse the
    same dynamic-threshold input as the pipeline.
    """

    if not stats.token_usage or not stats.token_usage.last_call:
        return None

    last_prompt = stats.token_usage.last_call.prompt_tokens
    if last_prompt <= 0:
        return None

    max_ctx = max_context_tokens if max_context_tokens and max_context_tokens > 0 else 128_000
    usage_pct = (last_prompt / max_ctx) * 100

    if usage_pct >= 90:
        health = "critical"
    elif usage_pct >= 80:
        health = "warning"
    else:
        health = "healthy"

    return ContextBudgetSnapshot(
        current_tokens=last_prompt,
        max_context_tokens=max_ctx,
        usage_percent=usage_pct,
        health_status=health,
        messages_estimated_tokens=messages_estimated_tokens,
        bound_tools_overhead_tokens=bound_tools_overhead_tokens,
        other_tokens=other_tokens,
        turn_count=turn_count,
        system_prompt_tokens=system_prompt_tokens,
        memory_tokens=memory_tokens,
        workspace_rules_tokens=workspace_rules_tokens,
        mcp_tools_tokens=mcp_tools_tokens,
        skills_tools_tokens=skills_tools_tokens,
        builtin_tools_tokens=builtin_tools_tokens,
    )


async def resolve_context_budget_breakdown(
    *,
    checkpointer: object | None,
    thread_id: str,
    cached_tools: object | None,
    provider_prompt_tokens: int,
    merged_context: dict[str, object] | str | None = None,
) -> dict[str, int]:
    """Resolve GUI breakdown: messages est., tool schema est., system/other remainder,

    along with fine-grained AgentLens 6-category breakdown (System / Memory / Rules / MCP / Skills).
    Also returns ``turn_count`` = number of human messages in the checkpoint, so
    the preflight can reuse the same dynamic-threshold input as compress_processor.
    """

    from myrm_agent_harness.utils.text_utils import get_token_count
    from myrm_agent_harness.utils.token_estimation import (
        estimate_messages_tokens,
        estimate_tool_schema_tokens,
    )

    messages_tokens = 0
    tools_tokens = 0
    turn_count = 0
    has_messages = False

    from myrm_agent_harness.runtime.checkpointing import read_checkpoint_messages

    raw_messages = await read_checkpoint_messages(checkpointer, thread_id)
    messages = [msg for msg in raw_messages if isinstance(msg, BaseMessage)]
    if messages:
        messages_tokens = estimate_messages_tokens(messages)
        turn_count = sum(1 for m in messages if m.type == "human")
        has_messages = True

    builtin_tokens = 0
    mcp_tokens = 0
    skills_tokens = 0

    if isinstance(cached_tools, Sequence) and cached_tools:
        for t in cached_tools:
            name = getattr(t, "name", "")
            if not name and isinstance(t, dict):
                fn = t.get("function")
                name = fn.get("name", "") if isinstance(fn, dict) else t.get("name", "")
            name_str = str(name)
            # The UI labels these rows as "… tools schema"; count the same wire schema.
            schema_tokens = estimate_tool_schema_tokens(t)
            tools_tokens += schema_tokens
            if name_str.startswith("mcp__") or "mcp" in name_str.lower():
                mcp_tokens += schema_tokens
            elif name_str.startswith("skill_") or "skill" in name_str.lower():
                skills_tokens += schema_tokens
            else:
                builtin_tokens += schema_tokens

    if not has_messages and tools_tokens <= 0:
        return {}

    other_tokens = max(0, provider_prompt_tokens - messages_tokens - tools_tokens)

    # Estimate fine-grained other sub-buckets from merged_context
    system_prompt_tokens = 0
    memory_tokens = 0
    workspace_rules_tokens = 0

    if isinstance(merged_context, dict):
        sp = merged_context.get("system_prompt")
        if isinstance(sp, str) and sp:
            system_prompt_tokens = get_token_count(sp)
        mem = merged_context.get("memory_context") or merged_context.get("retrieved_memory")
        if isinstance(mem, str) and mem:
            memory_tokens = get_token_count(mem)
        rules = merged_context.get("workspace_rules") or merged_context.get("project_rules")
        if isinstance(rules, str) and rules:
            workspace_rules_tokens = get_token_count(rules)
    elif isinstance(merged_context, str) and merged_context:
        import re

        sp_match = re.search(r"<system_prompt>([\s\S]*?)</system_prompt>", merged_context)
        if sp_match:
            system_prompt_tokens = get_token_count(sp_match.group(1))
        mem_match = re.search(r"<memory_context>([\s\S]*?)</memory_context>", merged_context)
        if mem_match:
            memory_tokens = get_token_count(mem_match.group(1))
        rules_match = re.search(r"<workspace_rules>([\s\S]*?)</workspace_rules>", merged_context)
        if rules_match:
            workspace_rules_tokens = get_token_count(rules_match.group(1))

    result: dict[str, int] = {
        "messages_estimated_tokens": messages_tokens,
        "bound_tools_overhead_tokens": tools_tokens,
        "other_tokens": other_tokens,
        "builtin_tools_tokens": builtin_tokens,
        "mcp_tools_tokens": mcp_tokens,
        "skills_tools_tokens": skills_tokens,
    }
    if system_prompt_tokens > 0:
        result["system_prompt_tokens"] = system_prompt_tokens
    if memory_tokens > 0:
        result["memory_tokens"] = memory_tokens
    if workspace_rules_tokens > 0:
        result["workspace_rules_tokens"] = workspace_rules_tokens

    # 仅在 checkpoint 真实可读时返回轮数，避免读取失败时前端误用 0 覆盖本地统计
    if has_messages:
        result["turn_count"] = turn_count
    return result
