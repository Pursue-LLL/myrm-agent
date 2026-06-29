"""App-layer assembly: creates and caches framework MemoryManager instances via Harness local storage.

[INPUT]
myrm_agent_harness.toolkits.memory.setup::create_local_memory_manager (POS: 开箱即用的本地记忆工厂)

[OUTPUT]
resolve_context_binding: 统一解析业务侧上下文绑定合同
create_memory_manager: 业务层记忆管理器工厂
create_memory_tools_for_user: 业务层记忆工具工厂
shutdown_cached_memory_managers: 释放进程级记忆管理器缓存

[POS]
业务层记忆适配器入口。通过 ContextBundle volume 的 memory scene 路径统一管理存储，
实现本地运行与沙箱挂载卷的无缝切换。Server 侧必须先解析出 `ResolvedContextBinding`，
再交给本层创建 MemoryManager。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol, cast

from myrm_agent_harness.toolkits.context_bundle.spec import DEFAULT_BUNDLE_ID
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    create_local_memory_manager,
)
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, RecallMode
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.core.memory.adapters.policy import (
    derive_binding_namespaces,
    resolve_scope_identifiers,
)
from app.core.memory.adapters.types import ResolvedContextBinding

logger = logging.getLogger(__name__)

_memory_manager_cache: dict[tuple[object, ...], MemoryManager] = {}
_memory_manager_cache_lock = asyncio.Lock()


class _CreateMemoryTools(Protocol):
    def __call__(self, manager: MemoryManager, *, recall_mode: RecallMode) -> list[object]: ...


def _memory_policy_signature(
    memory_policy: AgentMemoryPolicy | None,
) -> tuple[object, ...] | None:
    if memory_policy is None:
        return None
    read_scopes = tuple(scope.value for scope in memory_policy.read_scopes) if memory_policy.read_scopes else ()
    return (
        memory_policy.agent_id,
        memory_policy.channel_id,
        memory_policy.conversation_id,
        memory_policy.task_id,
        read_scopes,
        memory_policy.write_policy.value,
    )


def _manager_cache_key(
    *,
    base_path: Path,
    user_id: str,
    approval_required: bool,
    dedup_llm: object | None,
    embedding_config: EmbeddingConfig,
    namespaces: list[str] | None,
    agent_id: str | None,
    channel_id: str | None,
    conversation_id: str | None,
    task_id: str | None,
    memory_policy: AgentMemoryPolicy | None,
    recall_mode: RecallMode,
    time_decay_half_life_days: float | None = None,
) -> tuple[object, ...]:
    return (
        str(base_path.resolve()),
        user_id,
        approval_required,
        recall_mode.value,
        time_decay_half_life_days,
        embedding_config.model,
        embedding_config.api_key,
        embedding_config.api_base,
        id(dedup_llm) if dedup_llm is not None else None,
        tuple(namespaces or ()),
        agent_id,
        channel_id,
        conversation_id,
        task_id,
        _memory_policy_signature(memory_policy),
    )


async def create_memory_manager(
    binding: ResolvedContextBinding,
    embedding_config: EmbeddingConfig,
    *,
    approval_required: bool = False,
    dedup_llm: object | None = None,
    recall_mode: RecallMode = RecallMode.HYBRID,
    time_decay_half_life_days: float | None = None,
) -> MemoryManager:
    """Create a MemoryManager wired to local/volume-backed storage.

    Uses `settings.database.memory_base_path` (configurable via MEMORY_BASE_PATH env var).
    In SaaS sandbox, the Control Plane injects the path (e.g., `/persistent/memory`).
    Locally, it defaults to `{state_dir}/memory`.
    """
    from myrm_agent_harness.toolkits.context_bundle import ContextBundleFacade

    from app.config.settings import settings

    facade = ContextBundleFacade.from_state_dir(
        settings.database.state_dir,
        ensure_layout=False,
    )
    base_path = facade.memory_path()
    cache_key = _manager_cache_key(
        base_path=base_path,
        user_id="sandbox_user",
        approval_required=approval_required,
        dedup_llm=dedup_llm,
        embedding_config=embedding_config,
        namespaces=binding.namespaces,
        agent_id=binding.agent_id,
        channel_id=binding.channel_id,
        conversation_id=binding.conversation_id,
        task_id=binding.task_id,
        memory_policy=binding.memory_policy,
        recall_mode=recall_mode,
        time_decay_half_life_days=time_decay_half_life_days,
    )

    async with _memory_manager_cache_lock:
        cached = _memory_manager_cache.get(cache_key)
        if cached is not None:
            return cached

        from app.core.retriever.vector.defaults import create_default_vector_store

        store = await create_default_vector_store()

        manager = await create_local_memory_manager(
            base_path=base_path,
            embedding_config=embedding_config,
            user_id="sandbox_user",
            approval_required=approval_required,
            dedup_llm=dedup_llm,
            namespaces=binding.namespaces,
            agent_id=binding.agent_id,
            channel_id=binding.channel_id,
            conversation_id=binding.conversation_id,
            task_id=binding.task_id,
            memory_policy=binding.memory_policy,
            recall_mode=recall_mode,
            vector_store=store,
            time_decay_half_life_days=time_decay_half_life_days,
        )

        _memory_manager_cache[cache_key] = manager

    enabled = manager.get_enabled_types()
    dedup_status = "smart" if dedup_llm else "simple"
    logger.warning(
        f"MemoryManager created: path={base_path}, types={[t.value for t in enabled]}, "
        f"approval={approval_required}, dedup={dedup_status}"
    )
    return manager


async def create_memory_tools_for_user(
    binding: ResolvedContextBinding,
    embedding_config: EmbeddingConfig,
    *,
    approval_required: bool = False,
    dedup_llm: object | None = None,
    recall_mode: RecallMode = RecallMode.HYBRID,
    time_decay_half_life_days: float | None = None,
) -> tuple[MemoryManager, list[object]]:
    """Create a MemoryManager and its agent tools in one call."""
    from myrm_agent_harness.toolkits import create_memory_tools

    create_memory_tools_fn = cast(_CreateMemoryTools, create_memory_tools)
    manager = await create_memory_manager(
        binding,
        embedding_config,
        approval_required=approval_required,
        dedup_llm=dedup_llm,
        recall_mode=recall_mode,
        time_decay_half_life_days=time_decay_half_life_days,
    )
    tools = create_memory_tools_fn(manager, recall_mode=recall_mode)
    return manager, tools


def resolve_context_binding(
    *,
    namespaces: list[str] | None,
    agent_id: str | None,
    channel_id: str | None,
    conversation_id: str | None,
    task_id: str | None,
    shared_context_ids: list[str] | None = None,
    memory_policy: AgentMemoryPolicy | None = None,
    bundle_id: str | None = None,
    task_workspace_root: str | None = None,
) -> ResolvedContextBinding:
    from myrm_agent_harness.toolkits.context_bundle import AgentContextOverlay

    normalized_shared_context_ids = list(
        dict.fromkeys(context_id.strip() for context_id in (shared_context_ids or []) if context_id.strip())
    )
    (
        resolved_agent_id,
        resolved_channel_id,
        resolved_conversation_id,
        resolved_task_id,
    ) = resolve_scope_identifiers(
        agent_id=agent_id,
        channel_id=channel_id,
        conversation_id=conversation_id,
        task_id=task_id,
        memory_policy=memory_policy,
    )
    overlay = (
        AgentContextOverlay(task_workspace_root=task_workspace_root, memory_scenes_pinned=True) if task_workspace_root else None
    )
    return ResolvedContextBinding(
        agent_id=resolved_agent_id or "default",
        namespaces=derive_binding_namespaces(
            namespaces=namespaces,
            shared_context_ids=normalized_shared_context_ids,
            agent_id=agent_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            task_id=task_id,
            memory_policy=memory_policy,
        ),
        shared_context_ids=normalized_shared_context_ids,
        memory_policy=memory_policy,
        channel_id=resolved_channel_id,
        conversation_id=resolved_conversation_id,
        task_id=resolved_task_id,
        bundle_id=bundle_id or DEFAULT_BUNDLE_ID,
        agent_overlay=overlay,
    )


async def shutdown_cached_memory_managers() -> None:
    """Close all cached MemoryManager instances and clear the cache."""
    async with _memory_manager_cache_lock:
        managers = list(_memory_manager_cache.values())
        _memory_manager_cache.clear()

    if not managers:
        return

    results = await asyncio.gather(*(manager.close() for manager in managers), return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Failed to close cached MemoryManager: %s", result)
