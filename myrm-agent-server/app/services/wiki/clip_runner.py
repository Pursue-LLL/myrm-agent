"""Wiki browser clip job orchestration (extension → raw/).

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.ingress (POS: clip ingress pipeline)
- app.services.wiki.vault_service (POS: wiki archiver + compile queue)
- app.services.wiki.dedup_runner (POS: incremental dedup after clip)

[OUTPUT]
- WikiClipJobRecord (POS: async job status for clip operations)

[POS] server.services.wiki — browser clip async job orchestration
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from myrm_agent_harness.toolkits.wiki.pipeline.ingress import (
    ClipAssetInput,
    ClipIngressRequest,
    ClipIngressResult,
    ClipMode,
    publish_clip_ingress,
)

logger = logging.getLogger(__name__)


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


_jobs: dict[str, WikiClipJobRecord] = {}
_lock = asyncio.Lock()


def _scope_key(agent_id: str | None) -> str:
    return agent_id or "__default__"


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
    job_id = uuid.uuid4().hex
    record = WikiClipJobRecord(job_id=job_id, state=WikiClipJobState.PENDING, agent_id=agent_id)
    async with _lock:
        _jobs[job_id] = record

    async def _run() -> None:
        record.state = WikiClipJobState.RUNNING
        try:
            from app.services.wiki.vault_service import get_wiki_archiver

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
                raw_path = archiver._structure.get_raw_file_path(ingress_result.relative_path)
                if raw_path.exists():
                    archiver._queue.add_batch([str(raw_path)])
                    archiver._compiler.start_background_worker()
            if ingress_result.written:
                from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan

                await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
            record.state = WikiClipJobState.SUCCEEDED
        except Exception as exc:
            logger.error("Wiki clip job %s failed: %s", job_id, exc)
            record.state = WikiClipJobState.FAILED
            record.error_message = str(exc)

    asyncio.create_task(_run())
    return job_id


def get_wiki_clip_job(job_id: str) -> WikiClipJobRecord | None:
    return _jobs.get(job_id)
