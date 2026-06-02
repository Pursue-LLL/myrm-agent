"""Local file search service.

[INPUT]
- myrm_agent_harness.toolkits.local_file_search (POS: indexer, search engine, config, models)
- myrm_agent_harness.toolkits.vector (POS: vector store)
- myrm_agent_harness.toolkits.retriever.embedding (POS: embedding service)
- myrm_agent_harness.toolkits.retriever.reranker (POS: reranker service)
- app.services.config (POS: config persistence)

[OUTPUT]
- LocalFileSearchService: singleton service managing index lifecycle
- get_local_file_search_service(): accessor

[POS]
Business-layer service for local file search. Manages the lifecycle of the indexer
and search engine, persists configuration via the config service, and provides
async indexing task management.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from myrm_agent_harness.toolkits.local_file_search import (
    FileRecord,
    IndexedDirectory,
    IndexStats,
    LocalFileIndexer,
    LocalFileSearchConfig,
    LocalFileSearchEngine,
)

logger = logging.getLogger(__name__)

CONFIG_KEY = "local_file_search"
FILE_RECORDS_KEY = "local_file_search_records"

_service_instance: LocalFileSearchService | None = None


class LocalFileSearchService:
    """Manages the local file search lifecycle: configuration, indexing, and search."""

    def __init__(self) -> None:
        self._config = LocalFileSearchConfig()
        self._indexer: LocalFileIndexer | None = None
        self._search_engine: LocalFileSearchEngine | None = None
        self._initialized = False
        self._indexing_task: asyncio.Task[IndexStats] | None = None

    @property
    def config(self) -> LocalFileSearchConfig:
        return self._config

    @property
    def indexer(self) -> LocalFileIndexer | None:
        return self._indexer

    @property
    def search_engine(self) -> LocalFileSearchEngine | None:
        return self._search_engine

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """Initialize the service: load config, create indexer and search engine."""
        if self._initialized and self._indexer is not None:
            return

        await self._load_config()

        if not self._config.get_enabled_directories():
            logger.info("Local file search: no directories configured, engine not created")
            self._initialized = True
            return

        await self._create_engine()

    async def _create_engine(self) -> None:
        """Create the indexer and search engine instances."""
        try:
            from myrm_agent_harness.toolkits.retriever.embedding import get_embedding_service
            from myrm_agent_harness.toolkits.vector.qdrant import create_vector_store

            from app.services.agent.platform_config import require_platform_embedding_config
            from app.services.config.service import config_service

            vector_config_raw = await config_service.get("vector_store")
            local_path = "./data/vector_store"
            if vector_config_raw and isinstance(vector_config_raw.value, dict):
                local_path = vector_config_raw.value.get("local_path", local_path)

            from myrm_agent_harness.toolkits.vector import VectorStoreConfig

            vs_config = VectorStoreConfig(local_path=local_path)
            vector_store = await create_vector_store(vs_config)
            if vector_store is None:
                logger.warning("Failed to create vector store for local file search")
                self._initialized = True
                return

            embedding_cfg = await require_platform_embedding_config()
            embedding_service = get_embedding_service(embedding_cfg)

            embedding_dim = 1536
            try:
                embedding_dim = embedding_service.dimension
            except (AttributeError, RuntimeError):
                logger.warning("Could not determine embedding dimension, using default %d", embedding_dim)

            self._indexer = LocalFileIndexer(
                vector_store=vector_store,
                embedding_service=embedding_service,
                config=self._config,
                embedding_dimension=embedding_dim,
            )

            await self._restore_file_records()

            reranker = None
            try:
                from myrm_agent_harness.toolkits.retriever.reranker import get_reranker_service

                from app.core.channel_bridge.config_loader import load_user_configs
                from app.core.channel_bridge.config_parsers import extract_retrieval_models

                user_configs = await load_user_configs()
                _, reranker_cfg = extract_retrieval_models(user_configs.retrieval_dict)
                if reranker_cfg is not None:
                    reranker = get_reranker_service(reranker_cfg)
            except Exception:
                logger.info("Reranker not available, using vector-only mode")

            self._search_engine = LocalFileSearchEngine(
                vector_store=vector_store,
                embedding_service=embedding_service,
                reranker=reranker,
            )

            self._initialized = True
            logger.info(
                "Local file search engine created (%d directories)",
                len(self._config.get_enabled_directories()),
            )

        except Exception as e:
            logger.warning("Failed to create local file search engine: %s", e)
            self._initialized = True

    async def _ensure_engine(self) -> None:
        """Ensure indexer and search_engine are initialized. Re-creates if needed."""
        if self._indexer is not None and self._search_engine is not None:
            return
        self._initialized = False
        await self.initialize()

    async def _load_config(self) -> None:
        """Load configuration from the config service."""
        try:
            from app.services.config.service import config_service

            record = await config_service.get(CONFIG_KEY)
            if record and isinstance(record.value, dict):
                self._config = LocalFileSearchConfig.model_validate(record.value)
                logger.info(
                    "Loaded local file search config: %d directories",
                    len(self._config.directories),
                )
        except Exception as e:
            logger.warning("Failed to load local file search config: %s", e)

    async def save_config(self) -> None:
        """Persist current configuration to the config service."""
        try:
            from app.services.config.service import config_service

            await config_service.set(
                CONFIG_KEY,
                self._config.model_dump(mode="json"),
                device_id="system",
            )
        except Exception as e:
            logger.warning("Failed to save local file search config: %s", e)

    async def _save_file_records(self) -> None:
        """Persist file records for restart recovery."""
        if not self._indexer:
            return
        try:
            from app.services.config.service import config_service

            records = [r.model_dump(mode="json") for r in self._indexer.file_records.values()]
            await config_service.set(FILE_RECORDS_KEY, {"records": records}, device_id="system")
        except Exception as e:
            logger.warning("Failed to save file records: %s", e)

    async def _restore_file_records(self) -> None:
        """Restore file records from persistence (startup recovery)."""
        if not self._indexer:
            return
        try:
            from app.services.config.service import config_service

            record = await config_service.get(FILE_RECORDS_KEY)
            if record and isinstance(record.value, dict):
                raw_records = record.value.get("records", [])
                if isinstance(raw_records, list):
                    file_records = [FileRecord.model_validate(r) for r in raw_records]
                    self._indexer.restore_records(file_records)
                    logger.info("Restored %d file records from persistence", len(file_records))
        except Exception as e:
            logger.warning("Failed to restore file records: %s", e)

    async def add_directory(self, path: str, recursive: bool = True) -> IndexedDirectory:
        """Add a directory to be indexed. Validates path existence."""
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"Directory does not exist: {path}")

        for existing in self._config.directories:
            if Path(existing.path).resolve() == resolved:
                raise ValueError(f"Directory already configured: {path}")

        directory = IndexedDirectory(path=str(resolved), recursive=recursive)
        self._config.directories.append(directory)
        await self.save_config()

        await self._ensure_engine()

        logger.info("Added directory for indexing: %s", resolved)
        return directory

    async def remove_directory(self, directory_id: str) -> bool:
        """Remove a directory and its indexed data."""
        target = None
        for d in self._config.directories:
            if d.id == directory_id:
                target = d
                break

        if target is None:
            return False

        self._config.directories = [
            d for d in self._config.directories if d.id != directory_id
        ]
        await self.save_config()

        if self._indexer:
            removed = await self._indexer.remove_directory(directory_id)
            await self._save_file_records()
            logger.info("Removed directory %s (%d files cleaned)", target.path, removed)

        return True

    async def update_directory(
        self,
        directory_id: str,
        enabled: bool | None = None,
        recursive: bool | None = None,
    ) -> IndexedDirectory | None:
        """Update directory settings."""
        for d in self._config.directories:
            if d.id == directory_id:
                if enabled is not None:
                    d.enabled = enabled
                if recursive is not None:
                    d.recursive = recursive
                await self.save_config()
                return d
        return None

    async def trigger_index(self) -> IndexStats:
        """Trigger an indexing run. Returns immediately if already indexing."""
        await self._ensure_engine()

        if self._indexer is None:
            raise RuntimeError("Indexer not initialized. Configure directories first.")

        if self._indexing_task and not self._indexing_task.done():
            return self._indexer.stats

        self._indexing_task = asyncio.create_task(self._run_index_with_persistence())
        return self._indexer.stats

    async def _run_index_with_persistence(self) -> IndexStats:
        """Run indexing and persist file records on completion."""
        if not self._indexer:
            return IndexStats()
        stats = await self._indexer.index_all()
        await self._save_file_records()
        return stats

    def get_stats(self) -> IndexStats:
        """Get current index statistics."""
        if self._indexer:
            return self._indexer.stats
        return IndexStats()


def get_local_file_search_service() -> LocalFileSearchService:
    """Get or create the singleton service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = LocalFileSearchService()
    return _service_instance
