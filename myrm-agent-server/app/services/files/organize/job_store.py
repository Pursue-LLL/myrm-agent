"""Persist organize jobs for rollback.

[INPUT]
- app.config.settings::settings.database.state_dir (POS: 本地状态目录 SSOT)
- app.services.files.organize.types::OrganizeJob (POS: organize 领域模型 SSOT)

[OUTPUT]
- create_job / load_job / update_job / get_latest_job_for_workspace / TTL prune

[POS]
Organize job JSON 持久化（state_dir/organize_jobs）。供 rollback 与 latest-job CTA。
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

from app.services.files.organize.types import OrganizeJob, OrganizeJobStatus, OrganizeMoveRecord

logger = logging.getLogger(__name__)

_JOB_TTL_SECONDS = 7 * 24 * 3600


def _jobs_dir() -> Path:
    from app.config.settings import settings

    base = Path(settings.database.state_dir).expanduser().resolve() / "organize_jobs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _job_path(job_id: str) -> Path:
    return _jobs_dir() / f"{job_id}.json"


def save_job(job: OrganizeJob) -> None:
    _job_path(job.job_id).write_text(job.model_dump_json(indent=2), encoding="utf-8")


def load_job(job_id: str) -> OrganizeJob | None:
    path = _job_path(job_id)
    if not path.is_file():
        return None
    return OrganizeJob.model_validate_json(path.read_text(encoding="utf-8"))


def create_job(workspace: str, scope_root: str, moves: list[OrganizeMoveRecord]) -> OrganizeJob:
    job = OrganizeJob(
        job_id=str(uuid.uuid4()),
        workspace=workspace,
        scope_root=scope_root,
        status=OrganizeJobStatus.APPLIED,
        moves=moves,
        created_at=time.time(),
    )
    save_job(job)
    _prune_expired_jobs()
    return job


def update_job(job: OrganizeJob) -> None:
    save_job(job)


def get_latest_job_for_workspace(workspace: str) -> OrganizeJob | None:
    ws_real = os.path.realpath(os.path.expanduser(workspace))
    latest: OrganizeJob | None = None
    for path in _jobs_dir().glob("*.json"):
        try:
            job = OrganizeJob.model_validate_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            continue
        if os.path.realpath(os.path.expanduser(job.workspace)) != ws_real:
            continue
        if job.status != OrganizeJobStatus.APPLIED:
            continue
        if latest is None or job.created_at > latest.created_at:
            latest = job
    return latest


def _prune_expired_jobs() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    for path in _jobs_dir().glob("*.json"):
        try:
            job = OrganizeJob.model_validate_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            path.unlink(missing_ok=True)
            continue
        if job.created_at < cutoff:
            path.unlink(missing_ok=True)
