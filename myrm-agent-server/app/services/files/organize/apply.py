"""Apply workspace organize plans.

[INPUT]
- app.services.files.organize.validation::validate_organize_plan (POS: organize plan 六层路径校验)
- app.services.files.organize.job_store::create_job (POS: organize job 持久化)
- app.services.files.organize.wikilink::rewrite_wikilinks_in_tree (POS: wikilink 目标重写)
- _resolve_workspace (local): workspace root 解析 + 安全校验

[OUTPUT]
- apply_organize_plan: dry-run / 批量移动 / mid-batch 逆移
- rollback_organize_job: job 回滚 + partial_rollback 状态

[POS]
Workspace organize 批量执行与回滚。校验通过后 shutil.move；失败结构化 apply_failed；成功写 job 并重写 wikilink。
"""

from __future__ import annotations

import logging
import os
import shutil
import time

from app.services.files.organize.job_store import create_job, load_job, update_job
from app.services.files.organize.types import (
    OrganizeApplyResult,
    OrganizeJobStatus,
    OrganizeMoveRecord,
    OrganizePlan,
    OrganizeValidationIssue,
)
from app.services.files.organize.validation import validate_organize_plan
from app.services.files.organize.wikilink import rewrite_wikilinks_in_tree

logger = logging.getLogger(__name__)


def _resolve_workspace(workspace: str) -> str:
    """Resolve and validate workspace root (avoids api-layer import)."""
    from myrm_agent_harness.core.security.path_security import is_dangerous_path

    from app.core.utils.errors import validation_error

    resolved = os.path.realpath(os.path.expanduser(workspace))
    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied for workspace: {workspace}")
    if not os.path.isdir(resolved):
        raise validation_error(f"Workspace is not a directory: {workspace}")
    return resolved


def apply_organize_plan(workspace: str, plan: OrganizePlan, *, dry_run: bool) -> OrganizeApplyResult:
    ws = _resolve_workspace(workspace)
    issues = validate_organize_plan(ws, plan)
    if issues:
        return OrganizeApplyResult(dry_run=dry_run, issues=issues)

    preview_moves = [
        OrganizeMoveRecord(src=item.src, dst=item.dst) for item in plan.items
    ]
    if dry_run:
        return OrganizeApplyResult(
            dry_run=True,
            applied_count=len(preview_moves),
            moves=preview_moves,
        )

    applied: list[OrganizeMoveRecord] = []
    moved_pairs: list[tuple[str, str]] = []

    try:
        for item in plan.items:
            src_resolved = _resolve_item_path(ws, item.src)
            dst_resolved = _resolve_item_path(ws, item.dst)
            parent = os.path.dirname(dst_resolved)
            os.makedirs(parent, exist_ok=True)
            shutil.move(src_resolved, dst_resolved)
            applied.append(OrganizeMoveRecord(src=item.src, dst=item.dst))
            moved_pairs.append((src_resolved, dst_resolved))
    except OSError as exc:
        logger.error("Organize apply failed mid-batch: %s", exc)
        _rollback_moves(ws, applied)
        return OrganizeApplyResult(
            dry_run=False,
            issues=[
                OrganizeValidationIssue(
                    index=-1,
                    code="apply_failed",
                    message=str(exc),
                )
            ],
        )

    rewrite_wikilinks_in_tree(ws, moved_pairs)
    job = create_job(ws, plan.scope_root, applied)
    return OrganizeApplyResult(
        dry_run=False,
        job_id=job.job_id,
        applied_count=len(applied),
        moves=applied,
    )


def rollback_organize_job(job_id: str) -> OrganizeApplyResult:
    job = load_job(job_id)
    if job is None:
        from app.core.utils.errors import validation_error

        raise validation_error(f"Organize job not found: {job_id}")
    if job.status != OrganizeJobStatus.APPLIED:
        from app.core.utils.errors import validation_error

        raise validation_error(f"Job is not rollbackable: {job.status.value}")

    ws = os.path.realpath(os.path.expanduser(job.workspace))
    restored: list[OrganizeMoveRecord] = []
    rollback_pairs: list[tuple[str, str]] = []
    failed = False

    for move in reversed(job.moves):
        src_resolved = _resolve_item_path(ws, move.dst)
        dst_resolved = _resolve_item_path(ws, move.src)
        if not os.path.exists(src_resolved):
            failed = True
            continue
        parent = os.path.dirname(dst_resolved)
        os.makedirs(parent, exist_ok=True)
        try:
            shutil.move(src_resolved, dst_resolved)
            restored.append(OrganizeMoveRecord(src=move.dst, dst=move.src))
            rollback_pairs.append((src_resolved, dst_resolved))
        except OSError:
            failed = True

    if rollback_pairs:
        rewrite_wikilinks_in_tree(ws, rollback_pairs)

    job.status = (
        OrganizeJobStatus.PARTIAL_ROLLBACK if failed else OrganizeJobStatus.ROLLED_BACK
    )

    job.rolled_back_at = time.time()
    update_job(job)

    return OrganizeApplyResult(
        dry_run=False,
        job_id=job.job_id,
        job_status=job.status,
        applied_count=len(restored),
        moves=restored,
    )


def _rollback_moves(workspace: str, applied: list[OrganizeMoveRecord]) -> None:
    for move in reversed(applied):
        src_resolved = _resolve_item_path(workspace, move.dst)
        dst_resolved = _resolve_item_path(workspace, move.src)
        if os.path.exists(src_resolved):
            parent = os.path.dirname(dst_resolved)
            os.makedirs(parent, exist_ok=True)
            shutil.move(src_resolved, dst_resolved)


def _resolve_item_path(workspace: str, rel_or_abs: str) -> str:
    raw = rel_or_abs
    if not os.path.isabs(raw):
        raw = os.path.join(workspace, raw)
    return os.path.realpath(os.path.expanduser(raw))
