"""Memory brief preflight for General Agent streams.

[INPUT]
- app.ai_agents.agents::GeneralAgentParams (POS: General Agent 单轮执行参数)
- app.core.memory.adapters.setup::create_memory_manager, resolve_context_binding (POS: 业务层记忆管理器构建与命名空间绑定解析)

[OUTPUT]
- build_memory_brief_snapshot(): 生成同源 memory preview + snapshot（供 SSE 展示与执行复用）

[POS]
流式会话的记忆预检构建器。在首 token 前产出用户可见的 Memory Brief，并生成执行侧复用快照以保证简报与注入同源一致。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime

from app.ai_agents.agents import GeneralAgentParams
from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding

logger = logging.getLogger(__name__)

MemoryContextPayload = dict[str, object]
LearnedMemoryItem = dict[str, str]
LearnedMemoryPayload = dict[str, list[LearnedMemoryItem]]
MemoryBriefPreview = dict[str, object]
MemoryBriefSnapshot = dict[str, object]


def _normalize_learned_payload(raw: object) -> LearnedMemoryPayload:
    if not isinstance(raw, dict):
        return {"learned_rules": [], "learned_preferences": []}
    learned_rules_raw = raw.get("learned_rules", [])
    learned_prefs_raw = raw.get("learned_preferences", [])
    learned_rules = [item for item in learned_rules_raw if isinstance(item, dict)]
    learned_prefs = [item for item in learned_prefs_raw if isinstance(item, dict)]
    return {
        "learned_rules": learned_rules,
        "learned_preferences": learned_prefs,
    }


def _safe_ids(items: list[dict[str, str]], *, limit: int = 3) -> list[str]:
    output: list[str] = []
    for item in items:
        mem_id = item.get("id")
        if isinstance(mem_id, str) and mem_id.strip():
            output.append(mem_id.strip())
        if len(output) >= limit:
            break
    return output


def _snapshot_id(memory_ctx: MemoryContextPayload, learned_ctx: LearnedMemoryPayload) -> str:
    digest_input = {
        "memory_ctx": memory_ctx,
        "learned_ctx": learned_ctx,
    }
    raw = json.dumps(digest_input, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2s(raw, digest_size=10).hexdigest()


def _build_preview(
    *,
    snapshot_id: str,
    namespaces: list[str],
    memory_ctx: MemoryContextPayload,
    learned_ctx: LearnedMemoryPayload,
) -> MemoryBriefPreview:
    global_profile = memory_ctx.get("global_profile")
    if isinstance(global_profile, dict):
        profile_keys = sorted(str(key) for key in global_profile.keys())[:5]
    else:
        profile_keys = []

    instructions = memory_ctx.get("agent_instructions")
    rules = memory_ctx.get("rules")
    learned_prefs = learned_ctx.get("learned_preferences", [])
    learned_rules = learned_ctx.get("learned_rules", [])

    instructions_count = len(instructions) if isinstance(instructions, list) else 0
    rules_count = len(rules) if isinstance(rules, list) else 0
    correction_count = sum(1 for item in learned_prefs if item.get("source_error"))
    working_state = bool(memory_ctx.get("working_state"))

    is_cold_start = (
        not working_state
        and not profile_keys
        and instructions_count == 0
        and rules_count == 0
        and len(learned_prefs) == 0
        and len(learned_rules) == 0
    )

    return {
        "snapshot_id": snapshot_id,
        "generated_at_ms": int(datetime.now(tz=UTC).timestamp() * 1000),
        "namespaces": namespaces,
        "is_cold_start": is_cold_start,
        "stable": {
            "working_state": working_state,
            "profile_keys": profile_keys,
            "instruction_count": instructions_count,
            "rule_count": rules_count,
        },
        "learned": {
            "preference_count": len(learned_prefs),
            "rule_count": len(learned_rules),
            "correction_count": correction_count,
            "preference_ids": _safe_ids(learned_prefs),
            "rule_ids": _safe_ids(learned_rules),
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
    if params.embedding_config is None:
        return None

    effective_chat_id = (params.memory_conversation_id or params.chat_id or "").strip()
    if not effective_chat_id:
        return None

    workspace_root = params.declared_allowed_roots[0] if params.declared_allowed_roots else None
    binding = resolve_context_binding(
        namespaces=None,
        agent_id=params.agent_id or "default",
        channel_id=params.memory_channel_id or params.channel_name,
        conversation_id=effective_chat_id,
        task_id=params.memory_task_id,
        shared_context_ids=params.memory_shared_context_ids,
        memory_policy=params.memory_policy,
        task_workspace_root=workspace_root,
    )

    manager = await create_memory_manager(
        binding,
        params.embedding_config,
        approval_required=params.memory_require_confirmation,
    )

    static_result, learned_result = await asyncio.gather(
        manager.get_context(include_profile=True, include_rules=True, include_agent_instructions=True),
        manager.get_learned_context(),
        return_exceptions=True,
    )

    if isinstance(static_result, BaseException):
        logger.warning("Memory brief static context failed: %s", static_result)
        return None
    if isinstance(learned_result, BaseException):
        logger.warning("Memory brief learned context failed: %s", learned_result)
        learned_payload: LearnedMemoryPayload = {"learned_rules": [], "learned_preferences": []}
    else:
        learned_payload = _normalize_learned_payload(learned_result)

    if not isinstance(static_result, dict):
        logger.warning("Memory brief static context has unexpected type: %s", type(static_result).__name__)
        return None
    memory_payload = static_result
    snapshot_id = _snapshot_id(memory_payload, learned_payload)
    preview = _build_preview(
        snapshot_id=snapshot_id,
        namespaces=list(binding.namespaces),
        memory_ctx=memory_payload,
        learned_ctx=learned_payload,
    )
    snapshot: MemoryBriefSnapshot = {
        "snapshot_id": snapshot_id,
        "memory_ctx": memory_payload,
        "learned_ctx": learned_payload,
    }
    return preview, snapshot

