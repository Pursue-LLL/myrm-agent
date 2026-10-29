"""相对基线清单的增量备份包生成。

[INPUT]
- app.services.backup.full_stack_snapshot_exporter (POS: 存档包与清单类型)
- 标准库 hashlib / time / dataclasses (POS: 指纹比对与增量统计)

[OUTPUT]
- IncrementalBackupEngine.compute_incremental_diff: 把当前全量快照与基线清单逐项比对指纹，只收录变更项，并记录父级基线的 backup_id
- IncrementalDiffSummary: 新增、修改、未变化的统计

[POS]
未改动的实体不进增量包，增量包通过父级 backup_id 接在基线之后形成演进链。
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Mapping

from app.services.backup.full_stack_snapshot_exporter import (
    BackupArchiveBundle,
    BackupManifest,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncrementalDiffSummary:
    """增量比对差异统计信息。"""

    added_files: tuple[str, ...]
    modified_files: tuple[str, ...]
    unchanged_files_count: int


class IncrementalBackupEngine:
    """轻量差异增量备份引擎。"""

    @staticmethod
    def compute_incremental_diff(
        current_bundle: BackupArchiveBundle,
        base_manifest: BackupManifest,
        new_backup_id: str,
    ) -> BackupArchiveBundle:
        """比对当前全量快照与基准清单，生成仅含变更项的轻量增量包。"""
        base_hashes = base_manifest.file_hashes

        added: list[str] = []
        modified: list[str] = []
        unchanged_count = 0

        # 分类过滤函数：仅保留有改动或新增的项目
        def _filter_changed(category: str, store: Mapping[str, str]) -> dict[str, str]:
            nonlocal unchanged_count
            changed: dict[str, str] = {}
            for name, content in store.items():
                key = f"{category}/{name}"
                current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                base_hash = base_hashes.get(key)

                if base_hash is None:
                    # 新增实体
                    added.append(key)
                    changed[name] = content
                elif base_hash != current_hash:
                    # 修改过的实体
                    modified.append(key)
                    changed[name] = content
                else:
                    # 未改动，安全跳过
                    unchanged_count += 1
            return changed

        diff_db = _filter_changed("db", current_bundle.database_tables)
        diff_agents = _filter_changed("agent", current_bundle.agent_profiles)
        diff_skills = _filter_changed("skill", current_bundle.custom_skills)
        diff_crons = _filter_changed("cron", current_bundle.cron_schedules)
        diff_memory = _filter_changed("mem", current_bundle.memory_records)

        # 重新生成增量文件的指纹列表
        diff_hashes: dict[str, str] = {}
        for category, store in (
            ("db", diff_db),
            ("agent", diff_agents),
            ("skill", diff_skills),
            ("cron", diff_crons),
            ("mem", diff_memory),
        ):
            for name, content in store.items():
                key = f"{category}/{name}"
                diff_hashes[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # 计算增量总校验和 Checksum
        hasher = hashlib.sha256()
        hasher.update(new_backup_id.encode("utf-8"))
        hasher.update(current_bundle.manifest.app_version.encode("utf-8"))
        hasher.update(base_manifest.backup_id.encode("utf-8"))
        for k in sorted(diff_hashes.keys()):
            hasher.update(k.encode("utf-8"))
            hasher.update(diff_hashes[k].encode("utf-8"))
        incremental_checksum = hasher.hexdigest()

        diff_manifest = BackupManifest(
            manifest_version=current_bundle.manifest.manifest_version,
            app_version=current_bundle.manifest.app_version,
            backup_id=new_backup_id,
            created_at=time.time(),
            is_incremental=True,
            base_backup_id=base_manifest.backup_id,
            checksum=incremental_checksum,
            file_hashes=diff_hashes,
            entities_summary={
                "database_tables": len(diff_db),
                "agent_profiles": len(diff_agents),
                "custom_skills": len(diff_skills),
                "cron_schedules": len(diff_crons),
                "memory_records": len(diff_memory),
            },
            is_scrubbed=current_bundle.manifest.is_scrubbed,
            metadata={
                "base_backup_id": base_manifest.backup_id,
                "added_count": str(len(added)),
                "modified_count": str(len(modified)),
                "unchanged_count": str(unchanged_count),
            },
        )

        logger.info(
            "Computed incremental backup %s against base %s: added=%d, modified=%d, unchanged=%d",
            new_backup_id,
            base_manifest.backup_id,
            len(added),
            len(modified),
            unchanged_count,
        )

        return BackupArchiveBundle(
            manifest=diff_manifest,
            database_tables=diff_db,
            agent_profiles=diff_agents,
            custom_skills=diff_skills,
            cron_schedules=diff_crons,
            memory_records=diff_memory,
        )
