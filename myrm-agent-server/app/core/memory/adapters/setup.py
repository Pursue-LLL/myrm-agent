"""App-layer assembly: creates and caches framework MemoryManager instances via Harness local storage.

[INPUT]
myrm_agent_harness.toolkits.memory.setup::create_local_memory_manager (POS: 开箱即用的本地记忆工厂)

[OUTPUT]
resolve_context_binding: 统一解析业务侧上下文绑定合同
create_memory_manager: 业务层记忆管理器工厂
create_memory_tools_for_user: 业务层记忆工具工厂
shutdown_cached_memory_managers: 释放进程级记忆管理器缓存（联动清理 harness 嵌入式 Qdrant 单例）
evict_cached_memory_manager: 关闭并逐出指定 base_path 的 MemoryManager，联动释放对应嵌入式 Qdrant 单例（隔离评测卷专用）

[POS]
业务层记忆适配器入口。通过 ContextBundle volume 的 memory scene 路径统一管理存储，
实现本地运行与沙箱挂载卷的无缝切换。Server 侧必须先解析出 `ResolvedContextBinding`，
再交给本层创建 MemoryManager。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

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

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
        ConflictCallback,
        ConflictContext,
        ConsolidationCompleteCallback,
    )

logger = logging.getLogger(__name__)

# Conflicts whose importance reaches this threshold are treated as high-risk:
# they are never auto-resolved (auto_resolve_at stays None) and always require
# explicit user resolution, so critical preferences (stack moves, relocations,
# allergy changes) cannot be silently reverted to the stale old memory.
_HIGH_RISK_IMPORTANCE = 0.9
_CONFLICT_AUTO_RESOLVE_HOURS = 72

_memory_manager_cache: dict[tuple[object, ...], MemoryManager] = {}
_memory_manager_cache_lock = asyncio.Lock()


class _CreateMemoryTools(Protocol):
    def __call__(
        self, manager: MemoryManager, *, recall_mode: RecallMode
    ) -> list[object]: ...


def _memory_policy_signature(
    memory_policy: AgentMemoryPolicy | None,
) -> tuple[object, ...] | None:
    if memory_policy is None:
        return None
    read_scopes = (
        tuple(scope.value for scope in memory_policy.read_scopes)
        if memory_policy.read_scopes
        else ()
    )
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
    on_conflict: ConflictCallback | None = None,
    on_consolidation_complete: ConsolidationCompleteCallback | None = None,
    base_path: str | Path | None = None,
) -> MemoryManager:
    """Create a MemoryManager wired to local/volume-backed storage.

    Uses `settings.database.memory_base_path` (configurable via MEMORY_BASE_PATH env var).
    In SaaS sandbox, the Control Plane injects the path (e.g., `/persistent/memory`).
    Locally, it defaults to `{state_dir}/memory`.

    ``base_path`` overrides the storage root when the caller needs an isolated
    memory volume (e.g. evaluation runs that must never touch the user's real
    memory). When set, an embedded vector store is created inside the override
    directory so both relational and vector data stay fully isolated.
    """
    from myrm_agent_harness.toolkits.context_bundle import ContextBundleFacade

    from app.config.settings import settings

    facade = ContextBundleFacade.from_state_dir(
        settings.database.state_dir,
        ensure_layout=False,
    )
    default_base_path = Path(facade.memory_path()).resolve()
    base_path = default_base_path if base_path is None else Path(base_path).resolve()
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
            cached._on_conflict = on_conflict
            cached._on_consolidation_complete = on_consolidation_complete
            return cached

        from app.core.retriever.vector.defaults import create_default_vector_store

        # Isolated base_path (eval mode) → let harness embed vector store under
        # the override dir; default path → reuse the global volume vector store.
        is_isolated = base_path != default_base_path
        store = None if is_isolated else await create_default_vector_store()

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
            on_conflict=on_conflict,
            on_consolidation_complete=on_consolidation_complete,
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
    on_conflict: ConflictCallback | None = None,
    search_policy: object | None = None,
    search_backends: object | None = None,
    description_locale: str | None = None,
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
        on_conflict=on_conflict,
    )
    tool_kwargs: dict[str, object] = {"recall_mode": recall_mode}
    if search_policy is not None:
        tool_kwargs["search_policy"] = search_policy
    if search_backends is not None:
        tool_kwargs["search_backends"] = search_backends
    if description_locale is not None:
        tool_kwargs["description_locale"] = description_locale
    tools = create_memory_tools_fn(manager, **tool_kwargs)
    return manager, tools


def create_conflict_callback(agent_id: str | None = None) -> ConflictCallback:
    """Create an on_conflict callback that persists conflicts as PendingMemory rows.

    When the consolidation engine detects a high-importance contradiction it cannot
    auto-resolve, this callback writes a PendingMemory record with ``is_conflict=True``
    and returns ``ConflictResolution.PENDING`` so the framework keeps the old memory
    untouched until the user resolves it via the GUI.

    Low-risk conflicts (importance < ``_HIGH_RISK_IMPORTANCE``) get an
    ``conflict_auto_resolve_at`` deadline and are auto-resolved (keep_old) by the
    guardian if the user ignores them. High-risk conflicts keep ``conflict_auto_resolve_at``
    as None so they never silently auto-resolve — critical preferences (stack moves,
    relocations, allergy changes) always require explicit user action.
    """

    from myrm_agent_harness.toolkits.memory.types import ConflictResolution

    async def _on_conflict(ctx: ConflictContext) -> ConflictResolution:
        from datetime import UTC, timedelta
        from datetime import datetime as dt
        from uuid import uuid4

        from app.database.connection import get_session
        from app.database.models import PendingMemory

        conflict_id = str(uuid4())
        high_risk = (ctx.importance or 0.0) >= _HIGH_RISK_IMPORTANCE
        auto_resolve_at = (
            None
            if high_risk
            else dt.now(UTC) + timedelta(hours=_CONFLICT_AUTO_RESOLVE_HOURS)
        )

        try:
            async with get_session() as db:
                record = PendingMemory(
                    id=conflict_id,
                    agent_id=agent_id,
                    memory_type="semantic",
                    content=ctx.new_content,
                    metadata_json={
                        "merge_suggestion": ctx.merge_suggestion,
                        "source": "consolidation_conflict",
                    },
                    confidence=ctx.accuracy_score,
                    status="pending",
                    is_conflict=True,
                    conflict_old_memory_id=ctx.old_memory_id,
                    conflict_old_content=ctx.old_content,
                    conflict_accuracy_score=ctx.accuracy_score,
                    conflict_importance=ctx.importance,
                    conflict_auto_resolve_at=auto_resolve_at,
                )
                db.add(record)
                await db.commit()

            logger.info(
                "Conflict persisted as PendingMemory %s (old=%s, importance=%.2f, high_risk=%s, auto_resolve=%s)",
                conflict_id,
                ctx.old_memory_id,
                ctx.importance or 0.0,
                high_risk,
                auto_resolve_at,
            )
        except Exception:
            logger.warning(
                "Failed to persist conflict, falling back to KEEP_OLD", exc_info=True
            )
            return ConflictResolution.KEEP_OLD

        return ConflictResolution.PENDING

    return _on_conflict


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
        dict.fromkeys(
            context_id.strip()
            for context_id in (shared_context_ids or [])
            if context_id.strip()
        )
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
        AgentContextOverlay(
            task_workspace_root=task_workspace_root, memory_scenes_pinned=True
        )
        if task_workspace_root
        else None
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
    from myrm_agent_harness.toolkits.vector.qdrant import (
        clear_embedded_stores,
    )

    from app.core.memory.adapters.cascade import shutdown_cascade_manager

    async with _memory_manager_cache_lock:
        managers = list(_memory_manager_cache.values())
        _memory_manager_cache.clear()

    await shutdown_cascade_manager()

    results = await asyncio.gather(
        *(manager.close() for manager in managers), return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Failed to close cached MemoryManager: %s", result)

    # Embedded Qdrant stores are cached per path for process lifetime; the
    # process-level shutdown must release them so no QdrantClient survives.
    await clear_embedded_stores()


async def evict_cached_memory_manager(base_path: str | Path) -> None:
    """Close and evict any cached MemoryManager bound to ``base_path``.

    Used after an isolated evaluation run so its throwaway memory volume
    (SQLite + embedded vector store) is closed before the directory is removed.
    """
    from myrm_agent_harness.toolkits.vector.qdrant import (
        evict_embedded_store,
    )

    resolved = str(Path(base_path).resolve())

    async with _memory_manager_cache_lock:
        keys_to_close = [
            key
            for key in _memory_manager_cache
            if isinstance(key, tuple) and key and key[0] == resolved
        ]
        managers_to_close = [_memory_manager_cache.pop(key) for key in keys_to_close]

    results = await asyncio.gather(
        *(manager.close() for manager in managers_to_close), return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Failed to close evicted MemoryManager: %s", result)

    # The embedded Qdrant store created under the isolated volume lives in the
    # harness per-path singleton cache; release it so the directory can be
    # removed and no file handle is retained across evaluation runs.
    await evict_embedded_store(str(Path(base_path).resolve() / "vector_store"))
