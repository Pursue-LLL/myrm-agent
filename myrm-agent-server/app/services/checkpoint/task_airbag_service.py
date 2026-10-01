"""Server-layer orchestration and WAL persistence service for Task Safety Airbags.

Integrates with Harness TaskAirbagManager, manages task lifecycle hooks,
persists airbag manifests to disk (.myrm/airbag/{task_id}.json), and
provides crash recovery hydration for long-running autonomous runs.

[INPUT]
- myrm_agent_harness.api.security::arm_task_airbag (POS: 长任务挂机安全气囊武装与快照捕捉)
- myrm_agent_harness.api.security::rollback_task_airbag (POS: 长任务挂机时光倒流原子重置还原)
- myrm_agent_harness.api.security::get_task_airbag_diff (POS: 长任务变更反向 Diff 账本汇总)
- myrm_agent_harness.api.security::TaskAirbagManifest (POS: 挂机安全气囊元数据快照契约)
- myrm_agent_harness.api.security::TaskAirbagStatus (POS: 挂机安全气囊生命周期状态枚举)
- myrm_agent_harness.api.security::TaskAirbagDiffSummary (POS: 挂机安全气囊累积变更统计摘要)

[OUTPUT]
- TaskAirbagService: Singleton service managing airbag lifecycle and persistence.
- get_task_airbag_service: Service factory.

[POS]
Server-layer checkpoint & safety orchestration: unattended run airbag coordinator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from myrm_agent_harness.api.security import (
    TaskAirbagDiffSummary,
    TaskAirbagManifest,
    TaskAirbagStatus,
    arm_task_airbag,
    get_task_airbag_diff,
    rollback_task_airbag,
)

logger = logging.getLogger(__name__)

_AIRBAG_DIR_NAME = ".myrm/airbag"


class TaskAirbagService:
    """Manages pre-flight airbags for unattended tasks with disk persistence."""

    def __init__(self) -> None:
        self._active_manifests: dict[str, TaskAirbagManifest] = {}

    def _get_manifest_path(self, workspace_path: str, task_id: str) -> Path:
        return Path(workspace_path) / _AIRBAG_DIR_NAME / f"{task_id}.json"

    def _persist_manifest(self, manifest: TaskAirbagManifest) -> None:
        try:
            path = self._get_manifest_path(manifest.workspace_path, manifest.task_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "task_id": manifest.task_id,
                "workspace_path": manifest.workspace_path,
                "base_snapshot_id": manifest.base_snapshot_id,
                "is_git_repo": manifest.is_git_repo,
                "created_at_epoch_ms": manifest.created_at_epoch_ms,
                "status": manifest.status.value,
                "external_effects": list(manifest.external_effects),
            }
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temp_path.replace(path)
        except Exception as exc:
            logger.warning("Failed to persist airbag manifest for task '%s': %s", manifest.task_id, exc)

    def _load_manifest_from_disk(self, workspace_path: str, task_id: str) -> TaskAirbagManifest | None:
        try:
            path = self._get_manifest_path(workspace_path, task_id)
            if not path.exists():
                return None
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return TaskAirbagManifest(
                task_id=data["task_id"],
                workspace_path=data["workspace_path"],
                base_snapshot_id=data["base_snapshot_id"],
                is_git_repo=data["is_git_repo"],
                created_at_epoch_ms=data["created_at_epoch_ms"],
                status=TaskAirbagStatus(data.get("status", TaskAirbagStatus.ARMED.value)),
                external_effects=tuple(data.get("external_effects", [])),
            )
        except Exception as exc:
            logger.warning("Failed to load airbag manifest for task '%s': %s", task_id, exc)
            return None

    async def arm_airbag(self, task_id: str, workspace_path: str) -> TaskAirbagManifest | None:
        """Arm a safety airbag before starting an unattended task."""
        manifest = await arm_task_airbag(task_id, workspace_path)
        if manifest is None:
            return None

        self._active_manifests[task_id] = manifest
        self._persist_manifest(manifest)
        return manifest

    def record_external_effect(self, task_id: str, effect: str) -> None:
        """Record an external irreversible effect into the active airbag manifest."""
        manifest = self._active_manifests.get(task_id)
        if manifest and manifest.status == TaskAirbagStatus.ARMED:
            new_effects = list(manifest.external_effects)
            if effect not in new_effects:
                new_effects.append(effect)
                updated = manifest.with_external_effects(new_effects)
                self._active_manifests[task_id] = updated
                self._persist_manifest(updated)

    async def get_airbag_status(
        self, task_id: str, workspace_path: str | None = None
    ) -> TaskAirbagDiffSummary | None:
        """Query cumulative diff summary and status of an airbag."""
        manifest = self._active_manifests.get(task_id)
        if manifest is None and workspace_path:
            manifest = self._load_manifest_from_disk(workspace_path, task_id)
            if manifest:
                self._active_manifests[task_id] = manifest

        if manifest is None:
            return None

        return await get_task_airbag_diff(manifest)

    async def rollback_airbag(self, task_id: str, workspace_path: str | None = None) -> bool:
        """Trigger atomic time-travel rollback for a task to its pre-flight baseline."""
        manifest = self._active_manifests.get(task_id)
        if manifest is None and workspace_path:
            manifest = self._load_manifest_from_disk(workspace_path, task_id)
            if manifest:
                self._active_manifests[task_id] = manifest

        if manifest is None:
            logger.error("Cannot rollback: no airbag manifest found for task '%s'", task_id)
            return False

        success = await rollback_task_airbag(manifest)
        if success:
            updated = manifest.with_status(TaskAirbagStatus.ROLLED_BACK)
            self._active_manifests[task_id] = updated
            self._persist_manifest(updated)
            return True
        return False

    def dismiss_airbag(self, task_id: str, workspace_path: str | None = None) -> bool:
        """User confirms changes; safely dismisses the airbag."""
        manifest = self._active_manifests.get(task_id)
        if manifest is None and workspace_path:
            manifest = self._load_manifest_from_disk(workspace_path, task_id)

        if manifest is None:
            return False

        updated = manifest.with_status(TaskAirbagStatus.DISMISSED)
        self._active_manifests[task_id] = updated
        self._persist_manifest(updated)
        return True


_service_singleton: TaskAirbagService | None = None


def get_task_airbag_service() -> TaskAirbagService:
    """Return process-wide singleton of TaskAirbagService."""
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = TaskAirbagService()
    return _service_singleton
