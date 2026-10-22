"""Background export jobs with progress, cancellation and automatic cleanup.

[INPUT]
- app.services.instance_archive.export_service::build_export (POS: synchronous export pipeline)
- app.services.instance_archive.models::ArchivePaths (POS: exports directory)

[OUTPUT]
- ExportJob / JobState: observable state of one export
- ExportJobManager: start / get / cancel / discard / is_busy (one export at a time)
- get_export_manager: the single manager of a state directory, shared by the HTTP API and the scheduled backup
- ExportBusyError

[POS]
Exports of a large instance take minutes, so the HTTP request only starts a
worker thread and the UI polls progress. The finished archive stays on disk
until it is downloaded (or discarded); archives older than the TTL are swept so
abandoned exports never fill the volume.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from myrm_agent_harness.infra.state_archive import InsufficientSpaceError

from app.services.instance_archive.export_service import (
    ExportCancelledError,
    ExportProgress,
    ExportResult,
    build_export,
)
from app.services.instance_archive.models import ArchivePaths

logger = logging.getLogger(__name__)

_ARCHIVE_TTL_SECONDS = 6 * 3600


class JobState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportBusyError(RuntimeError):
    """An export is already running."""


@dataclass(slots=True)
class ExportJob:
    job_id: str
    created_at: float
    state: JobState = JobState.RUNNING
    progress: ExportProgress | None = None
    result: ExportResult | None = None
    error_code: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)  # set once the worker has finished, whatever the outcome


class ExportJobManager:
    def __init__(self, paths: ArchivePaths) -> None:
        self._paths = paths
        self._jobs: dict[str, ExportJob] = {}
        self._lock = threading.Lock()

    def start(
        self,
        *,
        user_id: str,
        app_version: str,
        deploy_mode: str,
        config_key: bytes | None,
        passphrase: str | None,
    ) -> ExportJob:
        with self._lock:
            if self.is_busy:
                raise ExportBusyError("An export is already running")
            self._sweep()
            job = ExportJob(job_id=uuid.uuid4().hex, created_at=time.time())
            self._jobs[job.job_id] = job
        dest = self._paths.exports / f"{job.job_id}.zip"
        thread = threading.Thread(
            target=self._run,
            args=(job, dest, user_id, app_version, deploy_mode, config_key, passphrase),
            name=f"instance-export-{job.job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return job

    @property
    def is_busy(self) -> bool:
        return any(job.state is JobState.RUNNING for job in list(self._jobs.values()))

    def get(self, job_id: str) -> ExportJob | None:
        return self._jobs.get(job_id)

    def archive_path(self, job: ExportJob) -> Path | None:
        return job.result.path if job.state is JobState.DONE and job.result is not None else None

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.cancel.set()

    def discard(self, job_id: str) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None:
            job.cancel.set()
            (self._paths.exports / f"{job_id}.zip").unlink(missing_ok=True)

    def _sweep(self) -> None:
        cutoff = time.time() - _ARCHIVE_TTL_SECONDS
        for job_id, job in list(self._jobs.items()):
            if job.state is not JobState.RUNNING and job.created_at < cutoff:
                self.discard(job_id)
        if self._paths.exports.is_dir():
            for leftover in self._paths.exports.iterdir():
                if leftover.stem not in self._jobs and leftover.stat().st_mtime < cutoff:
                    leftover.unlink(missing_ok=True)

    def _run(
        self,
        job: ExportJob,
        dest: Path,
        user_id: str,
        app_version: str,
        deploy_mode: str,
        config_key: bytes | None,
        passphrase: str | None,
    ) -> None:
        def on_progress(progress: ExportProgress) -> None:
            job.progress = progress

        try:
            job.result = build_export(
                state_dir=self._paths.state_dir,
                dest=dest,
                user_id=user_id,
                app_version=app_version,
                deploy_mode=deploy_mode,
                config_key=config_key,
                passphrase=passphrase,
                progress=on_progress,
                cancel=job.cancel,
            )
            job.state = JobState.DONE
        except ExportCancelledError:
            job.state = JobState.CANCELLED
        except InsufficientSpaceError:
            job.state, job.error_code = JobState.FAILED, "insufficient_space"
        except Exception:  # worker-thread boundary: an escaped error would leave the job running and block every later export
            logger.exception("[InstanceArchive] Export failed")
            job.state, job.error_code = JobState.FAILED, "export_failed"
        finally:
            job.done.set()


_managers: dict[Path, ExportJobManager] = {}


def get_export_manager(paths: ArchivePaths) -> ExportJobManager:
    """One manager per state directory, so a manual and a scheduled export never run together."""
    return _managers.setdefault(paths.state_dir, ExportJobManager(paths))
