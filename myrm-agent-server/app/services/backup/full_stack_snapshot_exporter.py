"""全资产快照存档的导出与凭据脱敏。

[INPUT]
- 标准库 hashlib / json / time / dataclasses (POS: 校验和、存档序列化与清单)

[OUTPUT]
- BackupManifest: 存档清单（备份标识、应用版本、是否增量及基线标识、整包校验和、逐项文件哈希、实体计数、是否已脱敏）
- BackupArchiveBundle: 清单与数据库表、智能体配置、自定义技能、定时任务、记忆五类内容
- SENSITIVE_KEY_SUBSTRINGS, REDACTED_PLACEHOLDER: 判定敏感键名的关键词与掩码占位符
- FullStackSnapshotExporter.export_snapshot: 把五类内容生成存档包，`scrub_credentials` 默认开启，键名含 api_key / token / secret / password 等的值替换为占位符

[POS]
导出的存档默认不含 API Key 与第三方 Token，且带校验和，恢复一侧可验证它没被改动。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Mapping

logger = logging.getLogger(__name__)

# 敏感字段脱敏匹配键名关键词
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "token",
    "secret",
    "password",
    "auth_credential",
    "private_key",
)
REDACTED_PLACEHOLDER: str = "***REDACTED***"


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """快照存档的顶层元数据清单。"""

    manifest_version: int
    app_version: str
    backup_id: str
    created_at: float
    is_incremental: bool
    base_backup_id: str | None
    checksum: str
    file_hashes: Mapping[str, str]
    entities_summary: Mapping[str, int]
    is_scrubbed: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BackupArchiveBundle:
    """完整的解包/打包归档载荷。"""

    manifest: BackupManifest
    database_tables: Mapping[str, str]
    agent_profiles: Mapping[str, str]
    custom_skills: Mapping[str, str]
    cron_schedules: Mapping[str, str]
    memory_records: Mapping[str, str]


class FullStackSnapshotExporter:
    """全资产一致性快照导出器。"""

    def __init__(self, app_version: str = "0.21.0") -> None:
        self.app_version = app_version

    @staticmethod
    def _scrub_sensitive_data(raw_json_str: str) -> str:
        """对 JSON 字符串内的敏感凭据递归进行掩码替换。"""
        try:
            data = json.loads(raw_json_str)
        except Exception:
            return raw_json_str

        def _walk_and_scrub(obj: object) -> object:
            if isinstance(obj, dict):
                cleaned: dict[str, object] = {}
                for k, v in obj.items():
                    key_lower = str(k).lower()
                    if any(sub in key_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                        cleaned[str(k)] = REDACTED_PLACEHOLDER
                    else:
                        cleaned[str(k)] = _walk_and_scrub(v)
                return cleaned
            if isinstance(obj, list):
                return [_walk_and_scrub(item) for item in obj]
            return obj

        scrubbed = _walk_and_scrub(data)
        return json.dumps(scrubbed, indent=2, sort_keys=True)

    def export_snapshot(
        self,
        backup_id: str,
        database_tables: Mapping[str, str],
        agent_profiles: Mapping[str, str],
        custom_skills: Mapping[str, str],
        cron_schedules: Mapping[str, str],
        memory_records: Mapping[str, str],
        scrub_credentials: bool = True,
        metadata: Mapping[str, str] | None = None,
    ) -> BackupArchiveBundle:
        """生成全资产结构化快照存档包。"""
        # 1. 可选敏感凭据脱敏处理
        processed_db = (
            {k: self._scrub_sensitive_data(v) for k, v in database_tables.items()} if scrub_credentials else dict(database_tables)
        )
        processed_agents = (
            {k: self._scrub_sensitive_data(v) for k, v in agent_profiles.items()} if scrub_credentials else dict(agent_profiles)
        )
        processed_skills = dict(custom_skills)
        processed_crons = (
            {k: self._scrub_sensitive_data(v) for k, v in cron_schedules.items()} if scrub_credentials else dict(cron_schedules)
        )
        processed_memory = dict(memory_records)

        # 2. 计算每个文件的 SHA256 哈希
        file_hashes: dict[str, str] = {}
        for category, store in (
            ("db", processed_db),
            ("agent", processed_agents),
            ("skill", processed_skills),
            ("cron", processed_crons),
            ("mem", processed_memory),
        ):
            for name, content in store.items():
                key = f"{category}/{name}"
                file_hashes[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # 3. 统计各领域实体数量
        entities_summary: dict[str, int] = {
            "database_tables": len(processed_db),
            "agent_profiles": len(processed_agents),
            "custom_skills": len(processed_skills),
            "cron_schedules": len(processed_crons),
            "memory_records": len(processed_memory),
        }

        # 4. 计算全局总检验和 Checksum
        hasher = hashlib.sha256()
        hasher.update(backup_id.encode("utf-8"))
        hasher.update(self.app_version.encode("utf-8"))
        for k in sorted(file_hashes.keys()):
            hasher.update(k.encode("utf-8"))
            hasher.update(file_hashes[k].encode("utf-8"))
        global_checksum = hasher.hexdigest()

        manifest = BackupManifest(
            manifest_version=1,
            app_version=self.app_version,
            backup_id=backup_id,
            created_at=time.time(),
            is_incremental=False,
            base_backup_id=None,
            checksum=global_checksum,
            file_hashes=file_hashes,
            entities_summary=entities_summary,
            is_scrubbed=scrub_credentials,
            metadata=dict(metadata or {}),
        )

        logger.info(
            "Exported snapshot %s: %d total files, checksum=%s",
            backup_id,
            len(file_hashes),
            global_checksum[:12],
        )

        return BackupArchiveBundle(
            manifest=manifest,
            database_tables=processed_db,
            agent_profiles=processed_agents,
            custom_skills=processed_skills,
            cron_schedules=processed_crons,
            memory_records=processed_memory,
        )
