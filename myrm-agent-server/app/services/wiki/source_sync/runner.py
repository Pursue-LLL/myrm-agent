"""Orchestrate wiki source sync runs.

[INPUT]
- app.services.wiki.source_sync.config_store (POS: per-agent wikiSourceSync UserConfig persistence)
- app.services.wiki.source_sync.state_store (POS: per-agent wikiSourceSyncState last-run observability)
- app.services.wiki.vault_resolver (POS: agent wiki vault path SSOT)
- myrm_agent_harness.toolkits.wiki.pipeline.raw_gate::publish_raw (POS: raw publication gate)

[OUTPUT]
- run_wiki_source_sync: Gmail/GDrive/RSS/mirror orchestration + optional compile enqueue + ingest SSE + persist scoped sync state

[POS]
Server SSOT for deterministic external-source pull into wiki raw/. Pull paths are zero-LLM;
compile enqueue requires a configured chat model when auto_compile is enabled.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.database.connection import get_session
from app.services.wiki.source_sync.config_store import load_wiki_source_sync_config
from app.services.wiki.source_sync.feishu import sync_feishu_docs_to_wiki
from app.services.wiki.source_sync.gdrive import sync_gdrive_folder_to_wiki
from app.services.wiki.source_sync.gmail import sync_gmail_label_to_wiki
from app.services.wiki.source_sync.integration_mirror import (
    mirror_integration_sync_results_to_wiki,
)
from app.services.wiki.source_sync.rss import sync_rss_feeds_to_wiki
from app.services.wiki.source_sync.schemas import (
    WikiSourceSyncConfig,
    WikiSourceSyncRunSummary,
)
from app.services.wiki.vault_resolver import resolve_wiki_vault_path

logger = logging.getLogger(__name__)


async def run_wiki_source_sync(
    *,
    llm: BaseChatModel | None,
    agent_id: str | None = None,
    config: WikiSourceSyncConfig | None = None,
    integration_sync_results: list[object] | None = None,
    sync_gmail_rss: bool = True,
) -> WikiSourceSyncRunSummary:
    async with get_session() as db:
        effective_config = config or await load_wiki_source_sync_config(
            db, agent_id=agent_id
        )

    structure = WikiStructure(resolve_wiki_vault_path(agent_id))
    compiler_enqueue: object | None = None
    archiver = None
    auto_compile = effective_config.auto_compile and llm is not None

    if llm is not None:
        from app.services.wiki.vault_service import get_wiki_archiver

        archiver = get_wiki_archiver(llm, agent_id=agent_id)
        structure = archiver._structure
        if auto_compile:
            compiler_enqueue = archiver._compiler
    elif effective_config.auto_compile:
        logger.warning(
            "Wiki source sync: auto_compile requested but no LLM configured; raw-only mode"
        )

    max_items = effective_config.max_items_per_run
    run = WikiSourceSyncRunSummary()

    if sync_gmail_rss and effective_config.gmail_enabled:
        gmail_result = await sync_gmail_label_to_wiki(
            structure,
            label=effective_config.gmail_label,
            max_items=max_items,
            auto_compile=auto_compile,
            compiler_enqueue=compiler_enqueue,
        )
        run.results.append(gmail_result)

    if sync_gmail_rss and effective_config.rss_feeds:
        rss_result = await sync_rss_feeds_to_wiki(
            structure,
            feed_urls=effective_config.rss_feeds,
            max_items=max_items,
            auto_compile=auto_compile,
            compiler_enqueue=compiler_enqueue,
        )
        run.results.append(rss_result)

    if sync_gmail_rss and effective_config.gdrive_enabled:
        gdrive_result = await sync_gdrive_folder_to_wiki(
            structure,
            folder_id=effective_config.gdrive_folder_id,
            max_items=max_items,
            auto_compile=auto_compile,
            compiler_enqueue=compiler_enqueue,
        )
        run.results.append(gdrive_result)

    if effective_config.feishu_enabled:
        feishu_result = await sync_feishu_docs_to_wiki(
            structure,
            folder_token=effective_config.feishu_folder_token,
            max_items=max_items,
            auto_compile=auto_compile,
            compiler_enqueue=compiler_enqueue,
        )
        run.results.append(feishu_result)

    if (
        effective_config.mirror_integrations_to_wiki
        and integration_sync_results
        and llm is not None
    ):
        from myrm_agent_harness.toolkits.memory.integration.types import (
            IntegrationSyncResult,
        )

        typed_results = [
            r for r in integration_sync_results if isinstance(r, IntegrationSyncResult)
        ]
        if typed_results:
            mirror_result = await mirror_integration_sync_results_to_wiki(
                typed_results,
                llm=llm,
                agent_id=agent_id,
                auto_compile=auto_compile,
            )
            run.results.append(mirror_result)

    run.total_published = sum(item.published for item in run.results)
    run.total_skipped = sum(item.skipped for item in run.results)
    run.total_failed = sum(item.failed for item in run.results)

    if run.total_published > 0 and archiver is not None:
        from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

        await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)

    if run.total_published > 0:
        try:
            from app.services.wiki.dedup_runner import run_wiki_dedup_scan_job

            await run_wiki_dedup_scan_job(agent_id=agent_id, incremental=True)
        except Exception as exc:
            logger.warning("Post source-sync wiki dedup scan failed: %s", exc)

    logger.info(
        "Wiki source sync finished: published=%d skipped=%d failed=%d",
        run.total_published,
        run.total_skipped,
        run.total_failed,
    )

    try:
        from app.services.wiki.source_sync.state_store import (
            save_wiki_source_sync_state,
            state_from_run_summary,
        )

        async with get_session() as db:
            await save_wiki_source_sync_state(
                db, state_from_run_summary(run), agent_id=agent_id
            )
    except Exception as exc:
        logger.warning("Failed to persist wiki source sync state: %s", exc)

    return run
