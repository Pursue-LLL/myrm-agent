"""Integration Memory service — Server-layer orchestration for integration data sync.

[INPUT]
- myrm_agent_harness.toolkits.memory.integration (POS: Integration Memory framework module)

[OUTPUT]
- IntegrationMemoryService: Server-layer facade for integration memory operations.
- IntegrationStatusTreeItem / IntegrationStatusSnapshot: Typed status DTOs.

[POS]
Business-layer service that wires framework-layer IntegrationFetcher, TreeManager,
and Summariser to server-specific infrastructure (embedding config, vector store,
graph store, LLM calls).  Provides a clean facade for API endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine

from myrm_agent_harness.toolkits.memory.graph.base import GraphStore
from myrm_agent_harness.toolkits.memory.integration.fetcher import IntegrationFetcher
from myrm_agent_harness.toolkits.memory.integration.protocols import IntegrationProvider
from myrm_agent_harness.toolkits.memory.integration.summarizer import IntegrationSummariser
from myrm_agent_harness.toolkits.memory.integration.tree_manager import IntegrationTreeManager
from myrm_agent_harness.toolkits.memory.integration.types import IntegrationSyncResult, IntegrationTree
from myrm_agent_harness.toolkits.memory.protocols.embedding import EmbeddingProtocol
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

SummariseFn = Callable[[str], Coroutine[None, None, str]]

_instance: IntegrationMemoryService | None = None


class IntegrationStatusTreeItem(BaseModel):
    tree_id: str
    provider: str
    account_key: str = ""
    leaf_count: int = 0
    root_summary: str = ""


class IntegrationStatusSnapshot(BaseModel):
    providers: list[str]
    provider_count: int
    tree_count: int
    total_indexed_items: int
    trees: list[IntegrationStatusTreeItem] = Field(default_factory=list)


class IntegrationTreeNodeDTO(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, str | int | float | bool]


class IntegrationMemoryService:
    """Server-layer facade for integration memory operations."""

    _VECTOR_COLLECTION = "integration_memory"

    def __init__(
        self,
        vector_store: VectorStoreProtocol,
        embedding: EmbeddingProtocol,
        graph_store: GraphStore,
        summarise_fn: SummariseFn | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._tree_manager = IntegrationTreeManager(graph_store)
        self._fetcher = IntegrationFetcher(
            vector_store=vector_store,
            embedding=embedding,
            tree_manager=self._tree_manager,
        )
        self._summariser: IntegrationSummariser | None = None
        if summarise_fn is not None:
            self._summariser = IntegrationSummariser(
                graph_store=graph_store,
                tree_manager=self._tree_manager,
                summarise_fn=summarise_fn,
            )
        self._bg_tasks: set[asyncio.Task] = set()

    def register_provider(self, provider: IntegrationProvider) -> None:
        self._fetcher.register_provider(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._fetcher.unregister_provider(provider_id)

    @property
    def provider_ids(self) -> list[str]:
        return self._fetcher.provider_ids

    async def sync_all(self, *, max_items: int = 200) -> list[IntegrationSyncResult]:
        results = await self._fetcher.sync(max_items_per_provider=max_items)
        for result in results:
            if result.created > 0 or result.updated > 0:
                # 1. Summarise integration tree
                if self._summariser:
                    try:
                        await self._summariser.summarise_tree(result.tree_id)
                    except Exception as exc:
                        logger.warning("Post-sync summarisation failed for tree %s: %s", result.tree_id, exc)
                
                # 2. Automated Knowledge Seeding via Extractor (No-Op Default)
                task = asyncio.create_task(self._auto_seed_knowledge(result))
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
        return results

    async def sync_provider(
        self,
        provider_id: str,
        *,
        account_key: str = "",
        max_items: int = 200,
    ) -> IntegrationSyncResult:
        result = await self._fetcher.sync_provider(
            provider_id, account_key=account_key, max_items=max_items
        )
        if result.created > 0 or result.updated > 0:
            # 1. Summarise integration tree
            if self._summariser:
                try:
                    await self._summariser.summarise_tree(result.tree_id)
                except Exception as exc:
                    logger.warning("Post-sync summarisation failed for tree %s: %s", result.tree_id, exc)
            
            # 2. Automated Knowledge Seeding via Extractor (No-Op Default)
            task = asyncio.create_task(self._auto_seed_knowledge(result))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        return result

    async def _auto_seed_knowledge(self, result: IntegrationSyncResult) -> None:
        """Automated knowledge seeding from freshly fetched integration data.
        
        Passes up to 200 new items through the MemoryExtractor using the 
        No-Op Default mechanism to automatically extract high-value profile traits.
        """
        if not getattr(result, "new_items", None):
            return
            
        try:
            from myrm_agent_harness.agent._internals.memory_extraction import (
                create_extraction_llm_func,
                persist_extracted_memories,
            )
            from myrm_agent_harness.toolkits.memory.strategies.extractor import ExtractionConfig, MemoryExtractor

            from app.api.dependencies import get_optional_llm_for_user
            from app.core.memory.adapters.setup import get_or_create_memory_manager
            
            # Using the system's default LLM config
            llm = await get_optional_llm_for_user()
            if getattr(llm, "_llm_type", None) == "dummy":
                logger.debug("Skipping auto seed: LLM not configured")
                return
                
            memory_manager = await get_or_create_memory_manager()
            llm_func = create_extraction_llm_func(llm)
            
            # Use max 200 items to save tokens
            items_to_process = result.new_items[:200]
            
            formatted_chunks = []
            current_chars = 0
            # A safe token limit equivalent character count (e.g. roughly ~10k-15k tokens)
            max_chars = 50000 
            
            for item in items_to_process:
                src_type = item.get("type", "Document").strip() or "Document"
                title = item.get("title", "").strip()
                text = item.get("text", "").strip()
                
                header = f"[{src_type}"
                if title:
                    header += f": {title}"
                header += "]"
                
                chunk = f"{header}\\n{text}"
                chunk_len = len(chunk)
                
                if current_chars + chunk_len > max_chars:
                    if current_chars == 0:
                        # If the very first item is too large, truncate it to fit
                        formatted_chunks.append(chunk[:max_chars] + "...[TRUNCATED]")
                    else:
                        # Stop accumulating to stay within limit
                        break
                else:
                    formatted_chunks.append(chunk)
                    current_chars += chunk_len
                
            content = "\\n\\n---\\n\\n".join(formatted_chunks)
            
            # Create a synthetic message list acting as the user providing structured context
            messages = [{"role": "user", "content": f"Here is my recent data from {result.provider}:\\n\\n{content}"}]
            
            # Use default extractor configuration (which includes No-Op Default)
            config = ExtractionConfig()
            extractor = MemoryExtractor(config=config, llm_func=llm_func)
            
            extraction_result = await extractor.extract(messages)
            
            if extraction_result.memories:
                stored = await persist_extracted_memories(
                    extraction_result.memories, memory_manager, source_chat_id=None
                )
                logger.info(
                    "Automated Knowledge Seeding: Extracted %d memories from provider '%s' (stored %d)",
                    len(extraction_result.memories), result.provider, stored
                )
        except Exception as exc:
            logger.warning("Automated Knowledge Seeding failed for provider '%s': %s", result.provider, exc)

    def list_trees(self, *, provider: str = "") -> list[IntegrationTree]:
        return self._tree_manager.list_trees(provider=provider)

    async def get_tree_structure(self, tree_id: str) -> list[IntegrationTreeNodeDTO]:
        nodes = await self._tree_manager.get_tree_structure(tree_id)
        return [
            IntegrationTreeNodeDTO(
                id=n.id,
                labels=n.labels,
                properties={k: v for k, v in n.properties.items() if isinstance(v, (str, int, float, bool))},
            )
            for n in nodes
        ]

    async def remove_tree(self, tree_id: str) -> int:
        try:
            await self._vector_store.delete_by_filter(
                self._VECTOR_COLLECTION, {"tree_id": tree_id}
            )
        except Exception as exc:
            logger.warning("Failed to purge vectors for tree %s: %s", tree_id, exc)
        return await self._tree_manager.remove_tree(tree_id)

    async def remove_trees_by_provider(self, provider_id: str) -> int:
        """Remove all integration trees belonging to a specific provider.

        Returns total number of deleted elements across all trees.
        """
        trees = self._tree_manager.list_trees(provider=provider_id)
        if not trees:
            return 0
        total_deleted = 0
        for tree in trees:
            deleted = await self.remove_tree(tree.id)
            total_deleted += deleted
        logger.info(
            "Removed %d trees (%d elements) for provider '%s'",
            len(trees), total_deleted, provider_id,
        )
        return total_deleted

    def get_status(self) -> IntegrationStatusSnapshot:
        trees = self._tree_manager.list_trees()
        return IntegrationStatusSnapshot(
            providers=self._fetcher.provider_ids,
            provider_count=len(self._fetcher.provider_ids),
            tree_count=len(trees),
            total_indexed_items=sum(t.leaf_count for t in trees),
            trees=[
                IntegrationStatusTreeItem(
                    tree_id=t.id,
                    provider=t.provider,
                    account_key=t.account_key,
                    leaf_count=t.leaf_count,
                    root_summary=t.root_summary[:200] if t.root_summary else "",
                )
                for t in trees
            ],
        )


async def get_integration_memory_service() -> IntegrationMemoryService | None:
    """Return the singleton service instance, or None if not yet initialised."""
    return _instance


def set_integration_memory_service(service: IntegrationMemoryService) -> None:
    """Set the singleton instance (called during server startup)."""
    global _instance
    _instance = service
