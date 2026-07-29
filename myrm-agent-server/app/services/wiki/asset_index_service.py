"""Wiki asset indexing — vision caption provider wiring and batch index runner.

[INPUT]
myrm_agent_harness.toolkits.wiki.retrieval.asset_index::WikiAssetIndexer, AssetIndexResult
myrm_agent_harness.toolkits.llms.vision.fallback_engine::VisionFallbackEngine
app.core.channel_bridge.config_loader::_load_single_config
app.core.channel_bridge.model_resolver::resolve_model_config

[OUTPUT]
- build_wiki_asset_caption_provider(): AssetCaptionProvider | None
- run_wiki_asset_index(archiver): AssetIndexResult
- schedule_wiki_asset_index(archiver, agent_id=None): None — fire-and-forget for import
- wiki_asset_index_enabled(): bool

[POS]
Server business layer for Obsidian wiki/assets retrieval. Resolves user visionFallbackModel
and drives harness WikiAssetIndexer without coupling harness to product config stores.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.api import LLMConfig
from myrm_agent_harness.toolkits.llms.vision.fallback_engine import VisionFallbackEngine
from myrm_agent_harness.toolkits.wiki.retrieval.asset_index import AssetIndexResult

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.retrieval.asset_index import AssetCaptionProvider

    from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

_active_asset_index_tasks: dict[str, asyncio.Task[None]] = {}
_pending_asset_index_reschedule: set[str] = set()


class _LocalFileExecutor:
    async def read_file_bytes(self, path: str) -> bytes:
        return Path(path).read_bytes()


class _VisionAssetCaptionProvider:
    def __init__(self, engine: VisionFallbackEngine) -> None:
        self._engine = engine
        self._executor = _LocalFileExecutor()

    async def caption_file(self, path: Path) -> str:
        return await self._engine.describe_local_image(str(path), self._executor)


async def _resolve_vision_llm_config() -> LLMConfig | None:
    from app.core.channel_bridge.config_loader import _load_single_config
    from app.core.channel_bridge.model_resolver import resolve_model_config

    default_model_dict = await _load_single_config("default_model")
    if not default_model_dict or not isinstance(default_model_dict, dict):
        return None

    vision_cfg = default_model_dict.get("visionFallbackModel")
    if not vision_cfg or not isinstance(vision_cfg, dict):
        return None

    provider_id = str(vision_cfg.get("providerId", "")).strip()
    model_name = str(vision_cfg.get("model", "")).strip()
    if not provider_id or not model_name:
        return None

    providers_dict_raw = await _load_single_config("providers")
    providers_dict = providers_dict_raw if isinstance(providers_dict_raw, dict) else {}
    litellm_model = f"{provider_id}/{model_name}"
    model_cfg = resolve_model_config(providers_dict, model_override=litellm_model)
    return LLMConfig(
        model=model_cfg.model,
        api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
    )


async def build_wiki_asset_caption_provider() -> AssetCaptionProvider | None:
    llm_config = await _resolve_vision_llm_config()
    if llm_config is None:
        return None
    return _VisionAssetCaptionProvider(VisionFallbackEngine(llm_config))


async def wiki_asset_index_enabled() -> bool:
    import os

    if os.getenv("MYRM_WIKI_INDEX_IMAGES", "").strip().lower() in {"0", "false", "no"}:
        return False
    return await build_wiki_asset_caption_provider() is not None


async def ensure_archiver_asset_indexer(archiver: MemoryToWikiArchiver) -> None:
    """Attach WikiAssetIndexer to archiver when vision model is configured."""
    from myrm_agent_harness.toolkits.wiki.retrieval.asset_index import WikiAssetIndexer

    if archiver._asset_indexer is not None:
        return

    provider = await build_wiki_asset_caption_provider()
    if provider is None:
        return

    archiver._config = replace(archiver._config, enable_asset_index=True)
    vector_store = getattr(archiver._query_engine._indexer, "_vector", None)
    embedding = getattr(archiver._query_engine._indexer, "_embedding", None)
    archiver._asset_indexer = WikiAssetIndexer(
        archiver._structure,
        archiver._config,
        vector_store=vector_store,
        embedding=embedding,
        caption_provider=provider,
    )
    archiver._query_engine._asset_indexer = archiver._asset_indexer


async def run_wiki_asset_index(archiver: MemoryToWikiArchiver) -> AssetIndexResult:
    await ensure_archiver_asset_indexer(archiver)
    if archiver._asset_indexer is None:
        return AssetIndexResult(indexed=0, skipped=0, failed=0)
    result = await archiver._asset_indexer.index_all()
    logger.info(
        "Wiki asset index complete: indexed=%d skipped=%d failed=%d",
        result.indexed,
        result.skipped,
        result.failed,
    )
    return result


async def _run_asset_index_background(
    archiver: MemoryToWikiArchiver,
    vault_key: str,
    *,
    agent_id: str | None,
) -> None:
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot
    from app.services.wiki.structural_stats_cache import invalidate_structural_lint_cache

    try:
        while True:
            _pending_asset_index_reschedule.discard(vault_key)
            await run_wiki_asset_index(archiver)
            invalidate_structural_lint_cache(archiver._structure)
            await publish_wiki_ingest_snapshot(
                archiver,
                agent_id=agent_id,
                stats_refresh_required=True,
            )
            if vault_key not in _pending_asset_index_reschedule:
                break
            logger.info("Re-running wiki asset index for %s after concurrent import", vault_key)
    except Exception as exc:
        logger.error("Background wiki asset index failed for %s: %s", vault_key, exc)
    finally:
        _active_asset_index_tasks.pop(vault_key, None)


def schedule_wiki_asset_index(
    archiver: MemoryToWikiArchiver,
    *,
    agent_id: str | None = None,
) -> None:
    """Schedule asset indexing without blocking the HTTP response (import path)."""
    vault_key = str(archiver._structure.base_dir)
    existing = _active_asset_index_tasks.get(vault_key)
    if existing is not None and not existing.done():
        _pending_asset_index_reschedule.add(vault_key)
        logger.debug("Wiki asset index already running for %s; queued rerun", vault_key)
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("No running event loop; skipping background wiki asset index")
        return

    task = loop.create_task(_run_asset_index_background(archiver, vault_key, agent_id=agent_id))
    _active_asset_index_tasks[vault_key] = task
    logger.info("Scheduled background wiki asset index for %s", vault_key)
