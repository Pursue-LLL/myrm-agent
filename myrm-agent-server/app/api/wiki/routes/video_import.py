"""[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map::WikiMapEventType (POS: OKF 认知地图模块入口。提供 wiki/index.md, wiki/log.md, wiki/hot.md 与 wiki/SCHEMA.md 的确定性免 LLM 构建与刷新。)
- app.api.wiki.archiver_dependency::_get_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault)
- app.api.wiki.routes::vault_effects (POS: Wiki API route submodules.)
- app.api.wiki.routes.import_helpers::_schedule_post_import_dedup_scan / _validate_import_conflict_options (POS: folder/zip/obsidian/urls/video 五条导入路径共用；不感知具体来源。)
- app.api.wiki.routes.schemas_import::ImportVideoRequest / ImportVideoResponse (POS: Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian /)
- myrm_agent_harness.toolkits.wiki.pipeline.ingress::publish_video_url_ingress / VideoTranscriptUnavailableError (POS: Video subtitles to raw/; a video with no readable subtitles raises VideoTranscriptUnavailableError)

[OUTPUT]
- import_video: Import video transcript into Wiki as timestamped Markdown with SSRF security checks. Every failed import carries an error_code the video dialog localizes; a security block is told apart by its status instead.

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiMapEventType,
)

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import vault_effects
from app.api.wiki.routes.import_helpers import (
    _schedule_post_import_dedup_scan,
    _validate_import_conflict_options,
)
from app.api.wiki.routes.schemas_import import (
    ImportVideoRequest,
    ImportVideoResponse,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


@router.post("/import/video", response_model=ImportVideoResponse)
async def import_video(
    request: ImportVideoRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ImportVideoResponse:
    """Import video transcript into Wiki as timestamped Markdown with SSRF security checks."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    target_url = request.url.strip()
    if not target_url:
        raise HTTPException(status_code=400, detail="Video URL cannot be empty")

    from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
    from myrm_agent_harness.toolkits.wiki.pipeline.ingress import (
        VideoTranscriptUnavailableError,
        VideoUrlIngressRequest,
        publish_video_url_ingress,
    )
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawConflictPolicy

    ssrf_res = await async_validate_url_for_ssrf(target_url)
    if not ssrf_res.safe:
        # The error text goes back to API clients, so the guard's verdict stays in the log.
        logger.warning("Video import blocked by the SSRF guard: %s (%s)", target_url, ssrf_res.error)
        return ImportVideoResponse(
            success=False,
            url=target_url,
            status="error",
            error="This address cannot be imported",
            error_code="address_rejected",
            message="URL verification failed",
        )

    conflict_policy = RawConflictPolicy.SUPERSEDE if request.on_conflict == "supersede" else RawConflictPolicy.SKIP

    try:
        ingress_res = await publish_video_url_ingress(
            archiver._structure,
            VideoUrlIngressRequest(
                url=target_url,
                folder_path=request.folder_path,
                preferred_languages=tuple(request.preferred_languages),
                window_duration_seconds=request.window_duration_seconds,
                conflict_policy=conflict_policy,
                supersede_reason=request.supersede_reason,
                caller="settings",
            ),
        )
    except VideoTranscriptUnavailableError as exc:
        logger.warning("No transcript to import from %s: %s", target_url, exc)
        return ImportVideoResponse(
            success=False,
            url=target_url,
            status="error",
            error=str(exc),
            error_code="nothing_readable",
            message="Video transcript unavailable",
        )
    except Exception:
        # The error text goes back to API clients, so the cause stays in the log.
        logger.warning("Failed to extract or ingest video transcript for %s", target_url, exc_info=True)
        return ImportVideoResponse(
            success=False,
            url=target_url,
            status="error",
            error="Failed to import this video",
            error_code="import_failed",
            message="Video transcript extraction or ingestion failed",
        )

    if ingress_res.security_blocked:
        return ImportVideoResponse(
            success=False,
            url=target_url,
            relative_path=ingress_res.relative_path,
            status="security_blocked",
            error="Content blocked by security scanner",
            message="Security policy violation",
        )

    if ingress_res.conflict:
        return ImportVideoResponse(
            success=True,
            url=target_url,
            relative_path=ingress_res.relative_path,
            status="skipped_conflict",
            message="File already exists (skipped conflict)",
        )

    if ingress_res.superseded:
        raw_path = archiver._structure.get_raw_file_path(ingress_res.relative_path)
        archiver._queue.add_batch([raw_path])
        if request.auto_compile:
            archiver._compiler.start_background_worker()
        await vault_effects._after_wiki_vault_mutation(archiver, "import video (superseded)")
        await _schedule_post_import_dedup_scan(agent_id)
        return ImportVideoResponse(
            success=True,
            url=target_url,
            relative_path=ingress_res.relative_path,
            status="superseded",
            message="Video document superseded and enqueued",
        )

    if ingress_res.written:
        raw_path = archiver._structure.get_raw_file_path(ingress_res.relative_path)
        archiver._queue.add_batch([raw_path])
        if request.auto_compile:
            archiver._compiler.start_background_worker()
        else:
            vault_effects._refresh_wiki_cognitive_map(
                archiver,
                WikiMapEventType.IMPORT,
                "Imported video document without auto-compile",
                {"file": ingress_res.relative_path, "source": "video"},
            )
        await vault_effects._after_wiki_vault_mutation(archiver, "import video")
        await _schedule_post_import_dedup_scan(agent_id)
        return ImportVideoResponse(
            success=True,
            url=target_url,
            relative_path=ingress_res.relative_path,
            status="success",
            message="Video transcript imported and enqueued for compilation",
        )

    return ImportVideoResponse(
        success=False,
        url=target_url,
        relative_path=ingress_res.relative_path,
        status="error",
        error="Ingress was not written",
        error_code="import_failed",
        message="Unknown ingestion outcome",
    )
