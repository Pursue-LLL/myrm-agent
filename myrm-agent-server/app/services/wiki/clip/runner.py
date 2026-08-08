"""Wiki browser clip job orchestration (extension → raw/).

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.ingress (POS: clip ingress pipeline)
- app.services.wiki.vault (POS: wiki archiver + compile queue)
- app.services.wiki.dedup_runner (POS: incremental dedup after clip)

[OUTPUT]
- schedule_wiki_clip / get_wiki_clip_job (POS: async clip job orchestration)

[POS] app.services.wiki.clip — browser clip async job orchestration
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum

from myrm_agent_harness.toolkits.wiki.pipeline.ingress import (
    ClipAssetInput,
    ClipIngressRequest,
    ClipIngressResult,
    ClipMode,
    publish_clip_ingress,
)

logger = logging.getLogger(__name__)

_JOB_TTL_SEC = 3600.0
_MAX_JOBS = 500


class WikiClipJobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class WikiClipJobRecord:
    job_id: str
    state: WikiClipJobState
    agent_id: str | None = None
    result: ClipIngressResult | None = None
    error_message: str = ""
    finished_at: float | None = None


_jobs: dict[str, WikiClipJobRecord] = {}
_lock = asyncio.Lock()


async def _purge_stale_jobs() -> None:
    async with _lock:
        now = time.monotonic()
        terminal = {WikiClipJobState.SUCCEEDED, WikiClipJobState.FAILED}
        stale_ids = [
            job_id
            for job_id, record in _jobs.items()
            if record.state in terminal
            and record.finished_at is not None
            and now - record.finished_at > _JOB_TTL_SEC
        ]
        for job_id in stale_ids:
            del _jobs[job_id]

        if len(_jobs) <= _MAX_JOBS:
            return

        finished = sorted(
            (
                (record.finished_at or 0.0, job_id)
                for job_id, record in _jobs.items()
                if record.state in terminal
            ),
            key=lambda item: item[0],
        )
        overflow = len(_jobs) - _MAX_JOBS
        for _, job_id in finished[:overflow]:
            _jobs.pop(job_id, None)


async def schedule_wiki_clip(
    *,
    agent_id: str | None,
    source_url: str,
    title: str,
    clip_mode: ClipMode,
    html: str,
    markdown: str,
    folder_path: str,
    assets: tuple[ClipAssetInput, ...],
    queue_compile: bool,
) -> str:
    await _purge_stale_jobs()
    job_id = uuid.uuid4().hex
    record = WikiClipJobRecord(
        job_id=job_id, state=WikiClipJobState.PENDING, agent_id=agent_id
    )
    async with _lock:
        _jobs[job_id] = record

    async def _run() -> None:
        record.state = WikiClipJobState.RUNNING
        try:
            from app.services.wiki.vault import get_wiki_archiver

            archiver = get_wiki_archiver(None, agent_id=agent_id)
            ingress_result = await publish_clip_ingress(
                archiver._structure,
                ClipIngressRequest(
                    source_url=source_url,
                    title=title,
                    clip_mode=clip_mode,
                    html=html,
                    markdown=markdown,
                    folder_path=folder_path,
                    assets=assets,
                    agent_id=agent_id,
                ),
            )
            record.result = ingress_result
            if ingress_result.written and queue_compile:
                raw_path = archiver._structure.get_raw_file_path(
                    ingress_result.relative_path
                )
                if raw_path.exists():
                    archiver._queue.add_batch([str(raw_path)])
                    archiver._compiler.start_background_worker()
            if ingress_result.written:
                from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan
                from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

                await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
                await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
            record.state = WikiClipJobState.SUCCEEDED
        except Exception as exc:
            logger.error("Wiki clip job %s failed: %s", job_id, exc)
            record.state = WikiClipJobState.FAILED
            record.error_message = str(exc)
        finally:
            record.finished_at = time.monotonic()
            await _purge_stale_jobs()

    asyncio.create_task(_run())
    return job_id


def get_wiki_clip_job(job_id: str) -> WikiClipJobRecord | None:
    return _jobs.get(job_id)
