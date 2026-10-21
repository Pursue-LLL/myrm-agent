"""Agent Memory System — app layer.

[INPUT]
- app.core.memory.adapters.cascade::get_cascade_memory_manager, purge_project_memories (POS: Cascade memory manager and purge)
- app.core.memory.adapters.setup::create_memory_manager (POS: Memory manager factory)

[OUTPUT]
- create_memory_manager, get_cascade_memory_manager, purge_project_memories

[POS]
Provides concrete backend adapters for the framework's MemoryManager.
Framework types and manager: ``myrm_agent_harness.toolkits.memory``.
Embedding: ``myrm_agent_harness.toolkits.retriever.embedding.EmbeddingService``.
"""

from app.core.memory.adapters.cascade import get_cascade_memory_manager, purge_project_memories
from app.core.memory.adapters.setup import create_memory_manager

__all__ = [
    "create_memory_manager",
    "get_cascade_memory_manager",
    "purge_project_memories",
]
