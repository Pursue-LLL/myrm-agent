"""Kanban data garbage collection service.

Periodically cleans up stale data from archived/completed kanban tasks:
- task_events rows older than retention period for terminal tasks
- task_runs rows older than retention period for archived tasks
- workspace directories of archived tasks older than min age

Designed to be called from _db_maintenance_job (every 6 hours) and
once on startup warmup. Uses batched deletes to avoid long SQLite locks.

[INPUT]
- app.database.connection::get_session (POS: DB session factory)
- app.config.settings (POS: Application settings)

[OUTPUT]
- KanbanGCService: Stateless service with run_gc() entry point.

[POS]
Kanban 数据垃圾回收服务。定时清理已归档/已完成任务的过期事件、运行记录和工作区目录。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app.database.connection import get_session

logger = logging.getLogger(__name__)

_EVENT_BATCH_SIZE = 1000
_RUN_BATCH_SIZE = 500
_WORKSPACE_BATCH_SIZE = 50

_DEFAULT_EVENT_RETENTION_DAYS = 30
_DEFAULT_RUN_RETENTION_DAYS = 30
_DEFAULT_WORKSPACE_MIN_AGE_DAYS = 7


@dataclass
class GCStats:
    """Statistics from a single GC run."""

    events_deleted: int = 0
    runs_deleted: int = 0
    workspaces_deleted: int = 0
    workspace_bytes_freed: int = 0
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class KanbanGCService:
    """Stateless kanban garbage collection service."""

    async def run_gc(self) -> GCStats:
        """Execute a full GC pass: events → runs → workspaces."""
        start = time.monotonic()
        stats = GCStats()

        try:
            stats.events_deleted = await self.gc_task_events()
        except Exception as exc:
            logger.error("Kanban GC events failed: %s", exc, exc_info=True)
            stats.errors.append(f"events: {exc}")

        try:
            stats.runs_deleted = await self.gc_task_runs()
        except Exception as exc:
            logger.error("Kanban GC runs failed: %s", exc, exc_info=True)
            stats.errors.append(f"runs: {exc}")

        try:
            ws_deleted, bytes_freed = await self.gc_workspaces()
            stats.workspaces_deleted = ws_deleted
            stats.workspace_bytes_freed = bytes_freed
        except Exception as exc:
            logger.error("Kanban GC workspaces failed: %s", exc, exc_info=True)
            stats.errors.append(f"workspaces: {exc}")

        stats.duration_ms = (time.monotonic() - start) * 1000

        if stats.events_deleted or stats.runs_deleted or stats.workspaces_deleted:
            freed_mb = stats.workspace_bytes_freed / (1024 * 1024)
            logger.info(
                "Kanban GC: deleted %d events, %d runs, %d workspaces (freed ~%.1fMB) in %.0fms",
                stats.events_deleted,
                stats.runs_deleted,
                stats.workspaces_deleted,
                freed_mb,
                stats.duration_ms,
            )
        else:
            logger.debug("Kanban GC: nothing to clean (%.0fms)", stats.duration_ms)

        return stats

    async def gc_task_events(
        self,
        retention_days: int = _DEFAULT_EVENT_RETENTION_DAYS,
    ) -> int:
        """Delete old events for terminal tasks in batches.

        Only events belonging to tasks in terminal states (done/archived)
        and older than retention_days are removed. Events for active tasks
        are preserved to maintain a complete audit trail.
        """
        cutoff_iso = _cutoff_iso(retention_days)
        total_deleted = 0

        while True:
            async with get_session() as session:
                result = await session.execute(
                    text(
                        "DELETE FROM kanban_task_events WHERE rowid IN ("
                        "  SELECT e.rowid FROM kanban_task_events e"
                        "  JOIN kanban_tasks t ON e.task_id = t.id"
                        "  WHERE t.status IN ('completed', 'archived')"
                        "  AND e.created_at < :cutoff"
                        "  LIMIT :batch"
                        ")"
                    ),
                    {"cutoff": cutoff_iso, "batch": _EVENT_BATCH_SIZE},
                )
                batch_count = result.rowcount or 0
                await session.commit()

            total_deleted += batch_count

            if batch_count < _EVENT_BATCH_SIZE:
                break

            await asyncio.sleep(0)

        return total_deleted

    async def gc_task_runs(
        self,
        retention_days: int = _DEFAULT_RUN_RETENTION_DAYS,
    ) -> int:
        """Delete old runs for archived tasks in batches."""
        cutoff_iso = _cutoff_iso(retention_days)
        total_deleted = 0

        while True:
            async with get_session() as session:
                result = await session.execute(
                    text(
                        "DELETE FROM kanban_task_runs WHERE rowid IN ("
                        "  SELECT r.rowid FROM kanban_task_runs r"
                        "  JOIN kanban_tasks t ON r.task_id = t.id"
                        "  WHERE t.status = 'archived'"
                        "  AND r.started_at < :cutoff"
                        "  LIMIT :batch"
                        ")"
                    ),
                    {"cutoff": cutoff_iso, "batch": _RUN_BATCH_SIZE},
                )
                batch_count = result.rowcount or 0
                await session.commit()

            total_deleted += batch_count

            if batch_count < _RUN_BATCH_SIZE:
                break

            await asyncio.sleep(0)

        return total_deleted

    async def gc_workspaces(
        self,
        min_age_days: int = _DEFAULT_WORKSPACE_MIN_AGE_DAYS,
    ) -> tuple[int, int]:
        """Clean up workspace directories of old archived tasks.

        Returns (directories_deleted, bytes_freed).
        Only removes workspace_path directories that are within the
        configured harness_dir (safety check against path traversal).
        Successfully cleaned entries have workspace_path set to NULL
        to avoid repeated scanning of already-removed directories.
        """
        from app.config.settings import settings

        harness_root = Path(settings.database.harness_dir).resolve()
        cutoff_iso = _cutoff_iso(min_age_days)

        total_deleted = 0
        total_bytes_freed = 0

        while True:
            async with get_session() as session:
                result = await session.execute(
                    text(
                        "SELECT id, workspace_path FROM kanban_tasks"
                        " WHERE status = 'archived'"
                        " AND workspace_path IS NOT NULL"
                        " AND workspace_path != ''"
                        " AND updated_at < :cutoff"
                        " LIMIT :batch"
                    ),
                    {"cutoff": cutoff_iso, "batch": _WORKSPACE_BATCH_SIZE},
                )
                rows = result.fetchall()

            if not rows:
                break

            cleaned_task_ids: list[str] = []

            for row in rows:
                task_id: str = row[0]
                ws_path_str: str = row[1]

                try:
                    ws_path = Path(ws_path_str).resolve()

                    try:
                        ws_path.relative_to(harness_root)
                    except ValueError:
                        logger.warning(
                            "Kanban GC: skipping workspace outside harness root: %s (task=%s)",
                            ws_path,
                            task_id[:8],
                        )
                        cleaned_task_ids.append(task_id)
                        continue

                    if not ws_path.exists() or not ws_path.is_dir():
                        cleaned_task_ids.append(task_id)
                        continue

                    dir_size = _dir_size_bytes(ws_path)
                    shutil.rmtree(ws_path, ignore_errors=True)

                    if not ws_path.exists():
                        total_deleted += 1
                        total_bytes_freed += dir_size
                        logger.debug("Kanban GC: removed workspace %s (task=%s)", ws_path, task_id[:8])

                    cleaned_task_ids.append(task_id)

                except Exception as exc:
                    logger.warning(
                        "Kanban GC: workspace cleanup failed for task %s: %s",
                        task_id[:8],
                        exc,
                    )

                await asyncio.sleep(0)

            if cleaned_task_ids:
                placeholders = ",".join(f":id_{i}" for i in range(len(cleaned_task_ids)))
                params = {f"id_{i}": tid for i, tid in enumerate(cleaned_task_ids)}
                async with get_session() as session:
                    await session.execute(
                        text(f"UPDATE kanban_tasks SET workspace_path = NULL WHERE id IN ({placeholders})"),
                        params,
                    )
                    await session.commit()

            if len(rows) < _WORKSPACE_BATCH_SIZE:
                break

            await asyncio.sleep(0)

        return total_deleted, total_bytes_freed


def _cutoff_iso(days: int) -> str:
    """Return ISO-8601 cutoff timestamp for parameterized SQL queries."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _dir_size_bytes(path: Path) -> int:
    """Estimate directory size in bytes (best-effort, recursive walk)."""
    try:
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
        return total
    except Exception:
        return 0
