"""Cascade-deletion MemoryManager singleton for purging memories by source_chat_id.

[INPUT]
myrm_agent_harness.toolkits.memory::{MemoryManager, open_local_graph_store} (POS: 记忆管理器框架；与记忆库同目录的主张图存储)
myrm_agent_harness.toolkits.memory.relational.sqlite_store (POS: SQLite 关系存储 - cascade 直接操作)
app.core.retriever.vector.defaults::create_default_vector_store (POS: 默认向量存储工厂)

[OUTPUT]
get_cascade_memory_manager: 获取全局级联删除专用 MemoryManager 单例
shutdown_cascade_manager: 关闭级联管理器并释放资源

[POS]
GDPR 遗忘权实现层。提供拥有该用户全部 scope 的 MemoryManager 单例，仅用于按 source_chat_id
元数据删除/计数记忆，无需 embedding 服务。MemoryManager 的元数据删除/计数会覆盖每个 embedding
模型的集合，所以该单例不必知道当前模型，切换模型后也无需重建。它与记忆写入方打开同一份主张图存储，
删除会话时才能一并清理由其任务摘要编译出的证据与主张。由 chat_disposal.py 在永久删除会话时调用。
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.toolkits.memory import MemoryManager, open_local_graph_store

logger = logging.getLogger(__name__)

_cascade_manager: MemoryManager | None = None
_cascade_manager_lock = asyncio.Lock()

# Only names the collections this manager would write; it never writes or embeds, and its
# deletions address every model's collections regardless.
_CASCADE_EMBEDDING_MODEL = "cascade-deletion"


async def get_cascade_memory_manager() -> MemoryManager:
    """Get the MemoryManager that owns every scope of the user, for cascade deletion operations.

    A deleted chat cannot say which agent, channel or project scope wrote a memory, so the manager owns all of
    them (``all_scopes``); a manager bound to the global scope alone would leave those memories behind.
    Embedding service is unused — cascade only performs metadata-based scroll/delete.
    """
    global _cascade_manager
    if _cascade_manager is not None:
        return _cascade_manager

    async with _cascade_manager_lock:
        if _cascade_manager is not None:
            return _cascade_manager

        from myrm_agent_harness.toolkits.context_bundle import ContextBundleFacade
        from myrm_agent_harness.toolkits.memory.config import MemoryConfig
        from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore

        from app.config.settings import settings
        from app.core.retriever.vector.defaults import create_default_vector_store

        facade = ContextBundleFacade.from_state_dir(settings.database.state_dir, ensure_layout=False)
        base_path = facade.memory_path()
        base_path.mkdir(parents=True, exist_ok=True)

        relational_store = SQLiteRelationalStore(db_path=str(base_path / "memory.db"))
        vector_store = await create_default_vector_store()

        config = MemoryConfig(embedding_model=_CASCADE_EMBEDDING_MODEL)
        _cascade_manager = MemoryManager(
            config=config,
            user_id="sandbox_user",
            namespaces=["global"],
            all_scopes=True,
            vector=vector_store,
            relational=relational_store,
            graph=open_local_graph_store(base_path),
            fts5_searcher=relational_store.search_fts5,
            auto_warmup=False,
        )
        return _cascade_manager


async def purge_project_memories(project_id: str) -> dict[str, int]:
    """Cascade-delete all memories belonging to a project's namespace."""
    clean_id = project_id.strip() if project_id else ""
    if not clean_id:
        return {}

    manager = await get_cascade_memory_manager()
    project_ns = f"project:{clean_id}"
    counts: dict[str, int] = {}
    try:
        # Purge by primary_namespace metadata
        c1 = await manager.delete_memories_by_metadata("primary_namespace", project_ns)
        for k, v in c1.items():
            counts[k] = counts.get(k, 0) + v

        # Also purge any memory tagged with project_id in flat metadata
        c2 = await manager.delete_memories_by_metadata("project_id", clean_id)
        for k, v in c2.items():
            counts[k] = counts.get(k, 0) + v
    except Exception as exc:
        logger.warning("Project memory purge failed (project=%s): %s", clean_id, exc)

    return counts


async def shutdown_cascade_manager() -> None:
    """Close the cascade manager if it exists."""
    global _cascade_manager
    if _cascade_manager is not None:
        mgr = _cascade_manager
        _cascade_manager = None
        try:
            await mgr.close()
        except Exception as e:
            logger.warning("Failed to close cascade manager: %s", e)
