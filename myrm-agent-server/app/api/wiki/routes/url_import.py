"""Wiki URL 导入路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiMapEventType,
)

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import shared
from app.api.wiki.routes.schemas_import import (
    ImportUrlsRequest,
    ImportUrlsResultResponse,
    UrlImportItemResult,
)
from app.api.wiki.routes.shared import (
    _schedule_post_import_dedup_scan,
    _validate_import_conflict_options,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


@router.post("/import/urls", response_model=ImportUrlsResultResponse)
async def import_urls(
    request: ImportUrlsRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ImportUrlsResultResponse:
    """Batch import web URLs into Wiki with SSRF protection, content extraction, and raw gate verification."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)

    cleaned_urls: list[str] = []
    seen: set[str] = set()
    for raw_url in request.urls:
        u = raw_url.strip()
        if not u:
            continue
        if u not in seen:
            seen.add(u)
            cleaned_urls.append(u)

    if not cleaned_urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
    if len(cleaned_urls) > 50:
        cleaned_urls = cleaned_urls[:50]

    from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
    from myrm_agent_harness.toolkits.wiki.pipeline.ingress import (
        UrlMarkdownIngressRequest,
        publish_url_markdown_ingress,
    )
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawConflictPolicy
    from myrm_agent_harness.toolkits.wiki.wiki_agent_tools import _fetch_url_as_markdown

    conflict_policy = RawConflictPolicy.SUPERSEDE if request.on_conflict == "supersede" else RawConflictPolicy.SKIP

    semaphore = asyncio.Semaphore(5)
    results: list[UrlImportItemResult] = []
    enqueued_paths: list[Path] = []
    skipped_conflict_count = 0
    superseded_count = 0
    security_blocked_count = 0
    security_redacted_count = 0
    error_count = 0

    async def _process_single_url(target_url: str) -> UrlImportItemResult:
        async with semaphore:
            try:
                ssrf_res = await async_validate_url_for_ssrf(target_url)
                if not ssrf_res.safe:
                    return UrlImportItemResult(
                        url=target_url,
                        status="error",
                        error=f"SSRF blocked or invalid URL: {ssrf_res.error}",
                    )

                try:
                    markdown = await _fetch_url_as_markdown(target_url)
                except Exception as exc:
                    logger.warning("_fetch_url_as_markdown failed for %s: %s", target_url, exc)
                    markdown = ""

                ingress_res = await publish_url_markdown_ingress(
                    archiver._structure,
                    UrlMarkdownIngressRequest(
                        url=target_url,
                        folder_path=request.folder_path,
                        conflict_policy=conflict_policy,
                        supersede_reason=request.supersede_reason,
                        caller="settings",
                    ),
                    markdown=markdown,
                )

                if ingress_res.security_blocked:
                    return UrlImportItemResult(
                        url=target_url,
                        relative_path=ingress_res.relative_path,
                        status="security_blocked",
                        error="Content blocked by security scanner",
                    )
                if ingress_res.conflict:
                    return UrlImportItemResult(
                        url=target_url,
                        relative_path=ingress_res.relative_path,
                        status="skipped_conflict",
                    )
                if ingress_res.superseded:
                    return UrlImportItemResult(
                        url=target_url,
                        relative_path=ingress_res.relative_path,
                        status="superseded",
                    )
                if ingress_res.written:
                    return UrlImportItemResult(
                        url=target_url,
                        relative_path=ingress_res.relative_path,
                        status=("security_redacted" if ingress_res.security_redacted else "success"),
                    )
                return UrlImportItemResult(
                    url=target_url,
                    relative_path=ingress_res.relative_path,
                    status="error",
                    error="Ingress was not written",
                )
            except Exception as exc:
                logger.warning("Failed to import URL %s: %s", target_url, exc)
                return UrlImportItemResult(
                    url=target_url,
                    status="error",
                    error=str(exc),
                )

    tasks = [_process_single_url(u) for u in cleaned_urls]
    batch_results = await asyncio.gather(*tasks)

    for item in batch_results:
        results.append(item)
        if item.status == "success":
            raw_path = archiver._structure.get_raw_file_path(item.relative_path)
            enqueued_paths.append(raw_path)
        elif item.status == "security_redacted":
            raw_path = archiver._structure.get_raw_file_path(item.relative_path)
            enqueued_paths.append(raw_path)
            security_redacted_count += 1
        elif item.status == "skipped_conflict":
            skipped_conflict_count += 1
        elif item.status == "superseded":
            raw_path = archiver._structure.get_raw_file_path(item.relative_path)
            enqueued_paths.append(raw_path)
            superseded_count += 1
        elif item.status == "security_blocked":
            security_blocked_count += 1
        elif item.status == "error":
            error_count += 1

    if enqueued_paths:
        archiver._queue.add_batch(enqueued_paths)
        if request.auto_compile:
            archiver._compiler.start_background_worker()
        else:
            shared._refresh_wiki_cognitive_map(
                archiver,
                WikiMapEventType.IMPORT,
                f"Imported {len(enqueued_paths)} URL document(s) without auto-compile",
                {"files_enqueued": len(enqueued_paths), "source": "urls"},
            )

    if enqueued_paths or superseded_count > 0:
        await shared._after_wiki_vault_mutation(archiver, "import urls")

    if enqueued_paths:
        await _schedule_post_import_dedup_scan(agent_id)

    message_parts = [f"Processed {len(cleaned_urls)} URL(s), {len(enqueued_paths)} enqueued"]
    if skipped_conflict_count:
        message_parts.append(f"{skipped_conflict_count} skipped (conflict)")
    if superseded_count:
        message_parts.append(f"{superseded_count} superseded")
    if security_blocked_count:
        message_parts.append(f"{security_blocked_count} security blocked")
    if security_redacted_count:
        message_parts.append(f"{security_redacted_count} security redacted")
    if error_count:
        message_parts.append(f"{error_count} failed")
    if request.auto_compile and enqueued_paths:
        message_parts.append("compilation started")

    return ImportUrlsResultResponse(
        success=True,
        total_urls=len(cleaned_urls),
        processed_count=len(cleaned_urls),
        enqueued_count=len(enqueued_paths),
        skipped_conflict_count=skipped_conflict_count,
        superseded_count=superseded_count,
        security_blocked_count=security_blocked_count,
        security_redacted_count=security_redacted_count,
        error_count=error_count,
        results=results,
        message=", ".join(message_parts),
    )
