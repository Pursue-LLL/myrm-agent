"""Batch image generation orchestrator.

5-state state machine for multi-prompt image generation:
  draft → reviewing → running → completed
                       ↕ paused
            → failed / cancelled

Concurrent execution via asyncio.Semaphore, pause/resume via asyncio.Event,
cancellation via per-job boolean flag, item-level timeout protection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from enum import Enum

import nanoid
from myrm_agent_harness.utils.coercion import parse_int
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BatchImageJob

logger = logging.getLogger(__name__)


def _exec_rowcount(result: object) -> int:
    rc = getattr(result, "rowcount", None)
    return rc if isinstance(rc, int) else 0


class BatchStatus(str, Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_VALID_TRANSITIONS: dict[BatchStatus, set[BatchStatus]] = {
    BatchStatus.DRAFT: {BatchStatus.REVIEWING, BatchStatus.CANCELLED},
    BatchStatus.REVIEWING: {BatchStatus.RUNNING, BatchStatus.CANCELLED},
    BatchStatus.RUNNING: {BatchStatus.PAUSED, BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED},
    BatchStatus.PAUSED: {BatchStatus.RUNNING, BatchStatus.CANCELLED},
    BatchStatus.COMPLETED: set(),
    BatchStatus.FAILED: {BatchStatus.RUNNING},
    BatchStatus.CANCELLED: set(),
}


class BatchPlanItem:
    """A single item in the batch generation plan."""

    __slots__ = ("index", "prompt", "model", "size", "quality", "status", "error", "media_id")

    def __init__(
        self,
        index: int,
        prompt: str,
        model: str | None = None,
        size: str | None = None,
        quality: str | None = None,
    ) -> None:
        self.index = index
        self.prompt = prompt
        self.model = model
        self.size = size
        self.quality = quality
        self.status: str = "pending"
        self.error: str | None = None
        self.media_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "prompt": self.prompt,
            "model": self.model,
            "size": self.size,
            "quality": self.quality,
            "status": self.status,
            "error": self.error,
            "media_id": self.media_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BatchPlanItem:
        item = cls(
            index=parse_int(data.get("index", 0), 0),
            prompt=str(data.get("prompt", "")),
            model=str(data["model"]) if data.get("model") else None,
            size=str(data["size"]) if data.get("size") else None,
            quality=str(data["quality"]) if data.get("quality") else None,
        )
        item.status = str(data.get("status", "pending"))
        item.error = str(data["error"]) if data.get("error") else None
        item.media_id = str(data["media_id"]) if data.get("media_id") else None
        return item


class BatchImageOrchestrator:
    """Orchestrates batch image generation jobs."""

    def __init__(self) -> None:
        self._running_jobs: dict[str, asyncio.Task[None]] = {}
        self._pause_events: dict[str, asyncio.Event] = {}
        self._cancel_flags: dict[str, bool] = {}

    async def recover_stale_jobs(self, session: AsyncSession) -> int:
        """Mark jobs left in running/paused state as failed after a restart."""
        stale_statuses = [BatchStatus.RUNNING.value, BatchStatus.PAUSED.value]
        stmt = (
            update(BatchImageJob)
            .where(BatchImageJob.status.in_(stale_statuses))
            .values(
                status=BatchStatus.FAILED.value,
                error_message="Interrupted by server restart",
                finished_at=datetime.now(UTC),
            )
        )
        result = await session.execute(stmt)
        count = _exec_rowcount(result)
        if count:
            await session.commit()
            logger.info("Recovered %d stale batch jobs after restart", count)
        return int(count)

    @staticmethod
    def _generate_id() -> str:
        return f"batch_{nanoid.generate(size=12)}"

    async def create_job(
        self,
        session: AsyncSession,
        items: list[dict[str, object]],
        *,
        concurrency: int = 3,
        session_id: str | None = None,
    ) -> BatchImageJob:
        """Create a new batch job in draft state."""
        job_id = self._generate_id()
        plan_items = [
            BatchPlanItem(
                index=i,
                prompt=str(item.get("prompt", "")),
                model=str(item["model"]) if item.get("model") else None,
                size=str(item["size"]) if item.get("size") else None,
                quality=str(item["quality"]) if item.get("quality") else None,
            )
            for i, item in enumerate(items)
        ]

        job = BatchImageJob(
            id=job_id,
            status=BatchStatus.DRAFT.value,
            plan=[item.to_dict() for item in plan_items],
            concurrency=min(max(concurrency, 1), 10),
            total_items=len(plan_items),
            session_id=session_id,
        )
        session.add(job)
        await session.flush()
        logger.info("Batch job created: %s (%d items)", job_id, len(plan_items))
        return job

    async def start_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> BatchImageJob:
        """Start executing a batch job (reviewing → running)."""
        job = await self._get_job(session, job_id)
        current = BatchStatus(job.status)
        if current not in (BatchStatus.REVIEWING, BatchStatus.FAILED):
            self._assert_transition(current, BatchStatus.RUNNING)

        job.status = BatchStatus.RUNNING.value
        job.started_at = datetime.now(UTC)
        await session.flush()
        await session.commit()

        pause_event = asyncio.Event()
        pause_event.set()
        self._pause_events[job_id] = pause_event
        self._cancel_flags[job_id] = False

        task = asyncio.create_task(self._execute_job(job_id))
        self._running_jobs[job_id] = task
        return job

    async def pause_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> BatchImageJob:
        """Pause a running job."""
        job = await self._get_job(session, job_id)
        self._assert_transition(BatchStatus(job.status), BatchStatus.PAUSED)
        job.status = BatchStatus.PAUSED.value
        await session.flush()

        if job_id in self._pause_events:
            self._pause_events[job_id].clear()

        logger.info("Batch job paused: %s", job_id)
        return job

    async def resume_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> BatchImageJob:
        """Resume a paused job."""
        job = await self._get_job(session, job_id)
        self._assert_transition(BatchStatus(job.status), BatchStatus.RUNNING)
        job.status = BatchStatus.RUNNING.value
        await session.flush()

        if job_id in self._pause_events:
            self._pause_events[job_id].set()

        logger.info("Batch job resumed: %s", job_id)
        return job

    async def cancel_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> BatchImageJob:
        """Cancel a job."""
        job = await self._get_job(session, job_id)
        self._assert_transition(BatchStatus(job.status), BatchStatus.CANCELLED)
        job.status = BatchStatus.CANCELLED.value
        job.finished_at = datetime.now(UTC)
        await session.flush()

        self._cancel_flags[job_id] = True
        if job_id in self._pause_events:
            self._pause_events[job_id].set()

        logger.info("Batch job cancelled: %s", job_id)
        return job

    async def get_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> BatchImageJob:
        """Get job by ID with user ownership check."""
        return await self._get_job(session, job_id)

    async def retry_failed(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> BatchImageJob:
        """Reset failed items to pending and restart the job."""
        job = await self._get_job(session, job_id)
        if job.status not in (BatchStatus.FAILED.value, BatchStatus.COMPLETED.value):
            raise ValueError(f"Can only retry from failed/completed state, current: {job.status}")

        plan_items = [BatchPlanItem.from_dict(d) for d in (job.plan or [])]
        reset_count = 0
        for item in plan_items:
            if item.status == "failed":
                item.status = "pending"
                item.error = None
                reset_count += 1

        if reset_count == 0:
            raise ValueError("No failed items to retry")

        job.plan = [item.to_dict() for item in plan_items]
        job.failed_items = 0
        await session.flush()
        logger.info("Batch job retry: %s (%d items reset)", job_id, reset_count)

        return await self.start_job(session, job_id)

    # -- Internal execution ---------------------------------------------------

    async def _execute_job(self, job_id: str) -> None:
        """Background task that executes pending items concurrently."""
        from app.platform_utils import get_session_factory

        factory = get_session_factory()
        try:
            async with factory() as session:
                job = await self._get_job(session, job_id)
                plan_items = [BatchPlanItem.from_dict(d) for d in (job.plan or [])]
                concurrency = job.concurrency
                semaphore = asyncio.Semaphore(concurrency)
                pause_event = self._pause_events.get(job_id)
                if pause_event is None:
                    pause_event = asyncio.Event()
                    pause_event.set()

                pending = [item for item in plan_items if item.status == "pending"]

                async def process_item(item: BatchPlanItem) -> None:
                    if self._cancel_flags.get(job_id, False):
                        return
                    await pause_event.wait()
                    if self._cancel_flags.get(job_id, False):
                        return

                    async with semaphore:
                        await self._generate_single_image(
                            session,
                            job,
                            item,
                            plan_items,
                        )

                tasks = [asyncio.create_task(process_item(item)) for item in pending]
                await asyncio.gather(*tasks, return_exceptions=True)

                if self._cancel_flags.get(job_id, False):
                    return

                completed = sum(1 for i in plan_items if i.status == "completed")
                failed = sum(1 for i in plan_items if i.status == "failed")

                job_refresh = await self._get_job(session, job_id)
                job_refresh.completed_items = completed
                job_refresh.failed_items = failed
                job_refresh.status = BatchStatus.FAILED.value if failed > 0 else BatchStatus.COMPLETED.value
                job_refresh.finished_at = datetime.now(UTC)
                await self._persist_plan(session, job_refresh, plan_items)
                await session.commit()
                logger.info(
                    "Batch job finished: %s (completed=%d, failed=%d)",
                    job_id,
                    completed,
                    failed,
                )
        except Exception as exc:
            logger.error("Batch job execution error: %s", job_id, exc_info=True)
            try:
                async with factory() as session:
                    job = await self._get_job(session, job_id)
                    job.status = BatchStatus.FAILED.value
                    job.error_message = str(exc)[:500]
                    job.finished_at = datetime.now(UTC)
                    await session.commit()
            except Exception:
                logger.error("Failed to mark batch job as failed: %s", job_id, exc_info=True)
        finally:
            self._running_jobs.pop(job_id, None)
            self._pause_events.pop(job_id, None)
            self._cancel_flags.pop(job_id, None)

    _ITEM_TIMEOUT_S = 180

    async def _generate_single_image(
        self,
        session: AsyncSession,
        job: BatchImageJob,
        item: BatchPlanItem,
        plan_items: list[BatchPlanItem],
    ) -> None:
        """Generate a single image and update the plan in-place."""
        item.status = "running"
        await self._persist_plan(session, job, plan_items)

        try:
            await asyncio.wait_for(
                self._do_generate(session, job, item),
                timeout=self._ITEM_TIMEOUT_S,
            )
            item.status = "completed"
        except TimeoutError:
            item.status = "failed"
            item.error = f"Generation timed out after {self._ITEM_TIMEOUT_S}s"
            logger.warning("Batch item %d timed out", item.index)
        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)[:500]
            logger.warning("Batch item %d failed: %s", item.index, exc)

        await self._persist_plan(session, job, plan_items)

    async def _do_generate(
        self,
        session: AsyncSession,
        job: BatchImageJob,
        item: BatchPlanItem,
    ) -> None:
        """Core generation logic, wrapped by timeout in _generate_single_image."""
        from myrm_agent_harness.toolkits.llms.image import ImageGenerationConfig, ImageGenerator

        config = ImageGenerationConfig(
            model=item.model or "dall-e-3",
            default_size=item.size or "1024x1024",
            default_quality=item.quality or "standard",
            max_retries=1,
        )
        generator = ImageGenerator(config)
        result = await generator.generate(item.prompt)

        image_bytes = await result.to_bytes()
        if image_bytes:
            from app.core.media.service import media_library_service

            record = await media_library_service.save_media(
                session,
                image_bytes=image_bytes,
                content_type="image/png",
                prompt=result.revised_prompt or item.prompt,
                model=result.model,
                resolution=item.size,
                source="batch_generate",
                session_id=job.session_id,
                batch_job_id=job.id,
            )
            item.media_id = record.id

    async def _persist_plan(
        self,
        session: AsyncSession,
        job: BatchImageJob,
        items: list[BatchPlanItem],
    ) -> None:
        """Write the current plan state back to DB."""
        job.plan = [item.to_dict() for item in items]
        await session.flush()

    async def _get_job(self, session: AsyncSession, job_id: str) -> BatchImageJob:
        stmt = select(BatchImageJob).where(BatchImageJob.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Batch job not found: {job_id}")
        return job

    @staticmethod
    def _assert_transition(current: BatchStatus, target: BatchStatus) -> None:
        if target not in _VALID_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid state transition: {current.value} → {target.value}")


batch_orchestrator = BatchImageOrchestrator()
