"""Business-specific vector store defaults.

[INPUT]
myrm_agent_harness.toolkits.vector (POS: 向量存储抽象层)
myrm_agent_harness.toolkits.vector.qdrant (POS: Qdrant 向量存储实现)

[OUTPUT]
get_default_vector_store_config: Embedded Qdrant config from settings.database.qdrant_path
create_default_vector_store: Convenience factory using default config

[POS]
业务层向量存储默认配置。路径来自 ``MYRM_DATA_DIR`` 派生的 ``settings.database.qdrant_path``。
"""

import logging
import os

from myrm_agent_harness.toolkits.vector import VectorStore, VectorStoreConfig
from myrm_agent_harness.toolkits.vector.config import DeploymentMode

from app.config.settings import settings

logger = logging.getLogger(__name__)


def get_default_vector_store_config() -> VectorStoreConfig:
    """Get embedded Qdrant configuration."""
    local_path = os.path.expanduser(settings.database.qdrant_path)
    return VectorStoreConfig(
        mode=DeploymentMode.EMBEDDED,
        local_path=local_path,
    )


async def create_default_vector_store() -> VectorStore | None:
    """Create vector store using default config.

    Returns:
        VectorStore instance, or None if embedded mode fails.
    """
    from myrm_agent_harness.toolkits.vector.qdrant import create_vector_store
    
    # Auto-cleanup stale locks before initializing
    try:
        from pathlib import Path
        # Import the cleanup script dynamically
        cleanup_script = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "cleanup_qdrant_locks.py"
        if cleanup_script.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("cleanup_qdrant_locks", cleanup_script)
            if spec and spec.loader:
                cleanup_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cleanup_module)
                # Clean up locks older than 0 seconds (force cleanup on startup)
                cleaned = cleanup_module.cleanup_qdrant_locks(settings.database.qdrant_path, max_age_seconds=0)
                if cleaned > 0:
                    logger.warning(f"Cleaned {cleaned} stale Qdrant lock files before initialization.")
    except Exception as e:
        logger.warning(f"Failed to auto-cleanup Qdrant locks: {e}")

    config = get_default_vector_store_config()
    store = await create_vector_store(config)
    if store is None:
        logger.warning("Failed to create embedded vector store (concurrent access detected). Memory system will be disabled.")
    return store
