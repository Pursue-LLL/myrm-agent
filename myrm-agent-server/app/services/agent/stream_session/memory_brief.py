"""Memory brief preflight for General Agent streams.

[INPUT]
- myrm_agent_harness.toolkits.memory.types::RuleSource (POS: 规则来源枚举，区分 agent 自存指令与其余规则)
- app.ai_agents.agents::GeneralAgentParams (POS: General Agent 单轮执行参数)
- app.core.memory.adapters.setup::create_memory_manager, resolve_context_binding (POS: 业务层记忆管理器构建与命名空间绑定解析)

[OUTPUT]
- build_memory_brief_snapshot(): 生成同源 memory preview + snapshot（供 SSE 展示与执行复用）

[POS]
流式会话的记忆预检构建器。在首 token 前产出用户可见的 Memory Brief，并生成执行侧复用快照以保证简报与注入同源一致。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.types import RuleSource

from app.ai_agents.agents import GeneralAgentParams
from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding

logger = logging.getLogger(__name__)

MemoryContextPayload = dict[str, object]
MemoryBriefPreview = dict[str, object]
MemoryBriefSnapshot = dict[str, object]


def _snapshot_id(memory_ctx: MemoryContextPayload) -> str:
    """Digest for execution snapshot — matches middleware inject (stable memory_ctx only)."""
    raw = json.dumps({"memory_ctx": memory_ctx}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2s(raw, digest_size=10).hexdigest()


def _entry_count(value: object) -> int:
    """Entries in a profile mapping; any other shape carries none."""
    return len(value) if isinstance(value, dict) else 0


def _rule_counts(rules: object) -> tuple[int, int]:
    """The (instructions the agent saved for itself, other rules) of the injected rule list; any other shape has none."""
    entries = [rule for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []
    instructions = sum(1 for rule in entries if rule.get("source") == RuleSource.AGENT_SELF.value)
    return instructions, len(entries) - instructions


def _build_preview(
    *,
    snapshot_id: str,
    namespaces: list[str],
    memory_ctx: MemoryContextPayload,
) -> MemoryBriefPreview:
    # The model is given every profile fact whichever namespace holds it: "global_profile" holds the global namespace,
    # "peer_profile" every other one (facts saved in chat land there). Counting one side would report an empty profile
    # for a user whose memory is in use.
    profile_count = _entry_count(memory_ctx.get("global_profile")) + _entry_count(memory_ctx.get("peer_profile"))
    instructions_count, rules_count = _rule_counts(memory_ctx.get("rules"))
    working_state_text = memory_ctx.get("working_state")
    working_state = isinstance(working_state_text, str) and bool(working_state_text)

    return {
        "snapshot_id": snapshot_id,
        "generated_at_ms": int(datetime.now(tz=UTC).timestamp() * 1000),
        "namespaces": namespaces,
        # Same rule as the injected block: it falls back to discovery guidance only when no section has content.
        "is_cold_start": not (working_state or profile_count or instructions_count or rules_count),
        "stable": {
            "working_state": working_state,
            "profile_count": profile_count,
            "instruction_count": instructions_count,
            "rule_count": rules_count,
        },
    }


async def build_memory_brief_snapshot(
    params: GeneralAgentParams,
) -> tuple[MemoryBriefPreview, MemoryBriefSnapshot] | None:
    """Build preview + same-source snapshot for a single stream turn.

    Returns:
      (preview, snapshot) when memory preflight is available.
      None when memory is disabled / unsupported for this request.
    """
    if not params.enable_memory or params.incognito_mode:
        return None

    effective_chat_id = (params.memory_conversation_id or params.chat_id or "").strip()
    if not effective_chat_id:
        return None

    binding = resolve_context_binding(
        namespaces=None,
        agent_id=params.agent_id or "default",
        channel_id=params.memory_channel_id or params.channel_name,
        conversation_id=effective_chat_id,
        task_id=params.memory_task_id,
        shared_context_ids=params.memory_shared_context_ids,
        memory_policy=params.memory_policy,
    )

    manager = await create_memory_manager(
        binding,
        params.embedding_config,
        approval_required=params.memory_require_confirmation,
    )

    try:
        static_context = await manager.get_context(include_profile=True, include_rules=True)
    except Exception as exc:
        logger.warning("Memory brief static context failed: %s", exc)
        return None

    memory_payload = dict(static_context)
    snapshot_id = _snapshot_id(memory_payload)
    preview = _build_preview(
        snapshot_id=snapshot_id,
        namespaces=list(binding.namespaces),
        memory_ctx=memory_payload,
    )
    snapshot: MemoryBriefSnapshot = {"snapshot_id": snapshot_id, "memory_ctx": memory_payload}
    return preview, snapshot
