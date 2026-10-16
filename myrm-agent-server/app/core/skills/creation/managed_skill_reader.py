"""Pre-batch snapshot reads from the storage skill_manage writes into.

[INPUT]
- app.core.skills.creation.service::SkillCreationService (POS: 本地技能写入根 base_path)
- myrm_agent_harness.core.security.path::safe_join_path (POS: 路径越界防护)

[OUTPUT]
- ManagedSkillSnapshotReader: skill_manage 批次改动前读取写入根里技能当前文件的快照读取器

[POS]
一轮对话的技能后端只列出该轮挂载的技能，读不到本轮新建的技能，也读不到不在智能体白名单内的技能；
据此拍的快照会把已有技能记成「批次前不存在」，撤销时整个技能被删。本读取器直接读写入器所在的目录，
快照因此就是回滚要还原的现场。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.core.security.path import safe_join_path

if TYPE_CHECKING:
    from app.core.skills.creation.service import SkillCreationService


class ManagedSkillSnapshotReader:
    """Reads skills from the root a ``SkillCreationService`` writes into; a missing file raises like a missing skill."""

    def __init__(self, creation_service: SkillCreationService) -> None:
        self._creation_service = creation_service

    def _skill_dir(self, skill_name: str) -> Path:
        # The root is read per call: the service's base_path is its single source of truth.
        return safe_join_path(self._creation_service.base_path, skill_name)

    async def get_skill_content(self, skill_name: str) -> str:
        return await asyncio.to_thread((self._skill_dir(skill_name) / SKILL_MD_FILE).read_text, encoding="utf-8")

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        return await asyncio.to_thread(safe_join_path(self._skill_dir(skill_name), path).read_bytes)
