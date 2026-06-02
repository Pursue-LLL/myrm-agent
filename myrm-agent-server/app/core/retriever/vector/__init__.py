"""Vector Store Toolkit — re-exports from myrm-agent-harness.

[INPUT]
myrm_agent_harness.toolkits.vector (POS: 向量存储抽象层)
myrm_agent_harness.toolkits.vector.qdrant (POS: Qdrant 向量存储实现)
app.core.retriever.vector.defaults (POS: 业务层向量存储默认配置)
app.core.retriever.vector.pool (POS: 向量存储连接池)

[OUTPUT]
Re-exports: VectorStore, VectorDocument, SearchResult, CollectionInfo,
    VectorStoreConfig, DeploymentMode, QdrantVectorStore,
    create_vector_store, VectorStorePool,
    get_default_vector_store_config, create_default_vector_store

[POS]
业务层向量存储入口。重新导出框架层的向量存储 API，并提供业务特定的默认配置和连接池。
"""

from myrm_agent_harness.toolkits.vector import (
    CollectionInfo,
    DeploymentMode,
    SearchResult,
    VectorDocument,
    VectorStore,
    VectorStoreConfig,
)
from myrm_agent_harness.toolkits.vector.pool import VectorStorePool
from myrm_agent_harness.toolkits.vector.qdrant import (
    QdrantVectorStore,
    create_vector_store,
)

from app.core.retriever.vector.defaults import (
    create_default_vector_store,
    get_default_vector_store_config,
)

__all__ = [
    # Base types (from harness)
    "CollectionInfo",
    "DeploymentMode",
    "SearchResult",
    "VectorDocument",
    "VectorStore",
    "VectorStoreConfig",
    "QdrantVectorStore",
    "create_vector_store",
    # Business defaults
    "create_default_vector_store",
    "get_default_vector_store_config",
    # Pool
    "VectorStorePool",
]
