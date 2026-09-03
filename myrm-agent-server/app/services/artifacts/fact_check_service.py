"""Fact Check Service for Deliverables.

[INPUT]
- myrm_agent_harness.core.artifacts.fact_check::FactCheckSheet, FactCheckItem, ConflictSeverity, ResolutionStatus
- myrm_agent_harness.core.artifacts.manifest::DeliverableItem, DeliverableCategory, DeliverableStatus
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault, VAULT_PREFIX

[OUTPUT]
- FactCheckService: class — 事实核查表持久化、双模生成 (JSON + Markdown) 与交付包挂载服务

[POS]
Server Business Layer — 将多源冲突核查表物化为标准 Vault 产物，并无缝集成进成套交付物清册 (DeliverableManifest)。
"""

from __future__ import annotations

import hashlib
import json
import logging

from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault
from myrm_agent_harness.api import (
    FactCheckSheet,
)
from myrm_agent_harness.core.artifacts.manifest import (
    DeliverableCategory,
    DeliverableItem,
    DeliverableStatus,
)

logger = logging.getLogger(__name__)


class FactCheckService:
    """事实核查表持久化与工件装配服务"""

    def __init__(self, vault: ArtifactVault) -> None:
        self.vault = vault

    def persist_fact_check_sheet(
        self,
        sheet: FactCheckSheet,
        *,
        relative_dir: str = "05_fact_check",
    ) -> list[DeliverableItem]:
        """将 FactCheckSheet 分别以 JSON 和 Markdown 格式持久化至 Vault，并生成对应的 DeliverableItem 列表.

        产出物：
        1. `05_fact_check/fact_check.json` (结构化数据供机器与前端交互组件解析)
        2. `05_fact_check/fact_check_report.md` (人类可读精美排版 Markdown)
        """
        items: list[DeliverableItem] = []

        # 1. 持久化 JSON 工件
        json_content = sheet.model_dump_json(indent=2)
        json_bytes = json_content.encode("utf-8")
        json_sha256 = hashlib.sha256(json_bytes).hexdigest()
        json_vault_uri = self.vault.put(
            content=json_bytes,
            filename="fact_check.json",
            content_type="application/json",
            description=f"{sheet.title} (JSON)",
        )

        json_item = DeliverableItem(
            id=f"fci_json_{sheet.sheet_id[:8]}",
            relative_path=f"{relative_dir}/fact_check.json",
            title=f"{sheet.title} (JSON 数据)",
            category=DeliverableCategory.FACT_CHECK,
            status=DeliverableStatus.VERIFIED,
            vault_uri=json_vault_uri,
            sha256_hash=json_sha256,
            size_bytes=len(json_bytes),
            mime_type="application/json",
            description=f"多源事实核查结构化清单 (共 {sheet.total_count} 项核查，{sheet.critical_count} 处严重冲突已仲裁)",
            metadata={
                "sheet_id": sheet.sheet_id,
                "critical_count": str(sheet.critical_count),
                "warning_count": str(sheet.warning_count),
                "unresolved_count": str(sheet.unresolved_count),
            },
        )
        items.append(json_item)

        # 2. 持久化 Markdown 报告工件
        md_content = sheet.to_markdown()
        md_bytes = md_content.encode("utf-8")
        md_sha256 = hashlib.sha256(md_bytes).hexdigest()
        md_vault_uri = self.vault.put(
            content=md_bytes,
            filename="fact_check_report.md",
            content_type="text/markdown",
            description=f"{sheet.title} 报告",
        )

        md_item = DeliverableItem(
            id=f"fci_md_{sheet.sheet_id[:8]}",
            relative_path=f"{relative_dir}/fact_check_report.md",
            title=f"{sheet.title} 报告",
            category=DeliverableCategory.FACT_CHECK,
            status=DeliverableStatus.VERIFIED,
            vault_uri=md_vault_uri,
            sha256_hash=md_sha256,
            size_bytes=len(md_bytes),
            mime_type="text/markdown",
            description="符合 GitHub 规范的多源事实核验与口径冲突比对报告",
            metadata={
                "sheet_id": sheet.sheet_id,
            },
        )
        items.append(md_item)

        return items

    def load_fact_check_sheet(self, vault_uri: str) -> FactCheckSheet | None:
        """从 Vault 中解析并还原 FactCheckSheet 对象."""
        if not vault_uri.startswith(VAULT_PREFIX):
            return None

        try:
            content_bytes = self.vault.get(vault_uri)
            data = json.loads(content_bytes.decode("utf-8"))
            return FactCheckSheet.model_validate(data)
        except Exception as e:
            logger.error("Failed to load FactCheckSheet from %s: %s", vault_uri, e)
            return None
