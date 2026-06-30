"""Agent Memory System — app layer.

Provides concrete backend adapters for the framework's MemoryManager.
Framework types and manager: ``myrm_agent_harness.toolkits.memory``.
Embedding: ``myrm_agent_harness.toolkits.retriever.embedding.EmbeddingService``.
"""

from app.core.memory.adapters.setup import create_memory_manager, get_cascade_memory_manager

__all__ = [
    "create_memory_manager",
    "get_cascade_memory_manager",
]
