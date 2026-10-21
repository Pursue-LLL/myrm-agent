"""Business-specific vector store defaults.

[INPUT]
myrm_agent_harness.toolkits.vector (POS: 向量存储抽象层)
myrm_agent_harness.toolkits.vector.qdrant (POS: Qdrant 向量存储实现)
app.config.system_status (POS: 全局系统状态单例)

[OUTPUT]
get_default_vector_store_config: Embedded Qdrant config from settings.database.qdrant_path
create_default_vector_store: Convenience factory using default config; flags an in-memory fallback in system_status

[POS]
业务层向量存储默认配置。路径来自 ``MYRM_DATA_DIR`` 派生的 ``settings.database.qdrant_path``。
"""

import os

from myrm_agent_harness.toolkits.vector import VectorStore, VectorStoreConfig
from myrm_agent_harness.toolkits.vector.config import DeploymentMode

from app.config.settings import settings
from app.config.system_status import system_status


def get_default_vector_store_config() -> VectorStoreConfig:
    """Get embedded Qdrant configuration."""
    local_path = os.path.expanduser(settings.database.qdrant_path)
    return VectorStoreConfig(
        mode=DeploymentMode.EMBEDDED,
        local_path=local_path,
    )


async def create_default_vector_store() -> VectorStore:
    """Create vector store using default config.

    The embedded store is a single-writer database: the harness holds an OS file lock on the
    data directory, the OS releases it when the holder exits, and a second process is refused
    and degrades to an in-memory store. A degraded store is reported through
    ``system_status.vector_degraded`` (shown to every user by the web UI) and by the memory
    command center. The lock file must never be deleted here: removing a held lock lets two
    processes write to one directory with diverging in-memory views and a last-writer-wins
    collection registry.

    Returns:
        The shared store; an in-memory one when the data directory cannot be opened.
    """
    from myrm_agent_harness.toolkits.vector.qdrant import create_vector_store

    store = await create_vector_store(get_default_vector_store_config())
    if not store.is_persistent:
        system_status.vector_degraded = True
    return store
