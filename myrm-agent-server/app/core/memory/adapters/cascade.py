"""Cascade-deletion MemoryManager singleton for purging memories by source_chat_id.

[INPUT]
myrm_agent_harness.toolkits.memory.MemoryManager (POS: 记忆管理器框架)
myrm_agent_harness.toolkits.memory.relational.sqlite_store (POS: SQLite 关系存储 - cascade 直接操作)
app.core.retriever.vector.defaults::create_default_vector_store (POS: 默认向量存储工厂)

[OUTPUT]
get_cascade_memory_manager: 获取全局级联删除专用 MemoryManager 单例
shutdown_cascade_manager: 关闭级联管理器并释放资源

[POS]
GDPR 遗忘权实现层。提供全局 namespace 的 MemoryManager 单例，仅用于按 source_chat_id
元数据删除/计数记忆，无需 embedding 服务。由 chat_crud.py 在永久删除会话时调用。
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.toolkits.memory import MemoryManager

logger = logging.getLogger(__name__)

_cascade_manager: MemoryManager | None = None
_cascade_manager_lock = asyncio.Lock()

_SEMANTIC_PREFIX = "memory_semantic_"


async def _infer_embedding_model(vector_store: object) -> str:
    """Infer the embedding model name from existing Qdrant collections.

    Looks for 'memory_semantic_{model}' and extracts the model suffix.
    Falls back to a sensible default if no collection is found.
    """
    try:
        collections: list[str] = await vector_store.list_collections()
        for name in collections:
            if name.startswith(_SEMANTIC_PREFIX):
                return name[len(_SEMANTIC_PREFIX):]
    except Exception as e:
        logger.warning("Failed to infer embedding model from collections: %s", e)
    return "text-embedding-3-small"


async def get_cascade_memory_manager() -> MemoryManager:
    """Get a global-scope MemoryManager for cascade deletion operations.

    Uses namespace=["global"] to reach all memories regardless of agent/channel scope.
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

        embedding_model = await _infer_embedding_model(vector_store)
        config = MemoryConfig(embedding_model=embedding_model)
        _cascade_manager = MemoryManager(
            config=config,
            user_id="sandbox_user",
            namespaces=["global"],
            vector=vector_store,
            relational=relational_store,
            auto_warmup=False,
        )
        return _cascade_manager


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
