"""批量导入技能会话的持久化暂存区。

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.batch_installer::HermesImportedSkill (POS: 批量 ZIP 解析出的技能 DTO)

[OUTPUT]
- SkillStagingManager: /preview 阶段将完整技能列表 pickle 落盘，/confirm 阶段反序列化还原，并负责过期会话清理
- SkillStagingManager._cleanup_expired_sessions_sync: 后台任务入口（>24h 无主 .pkl 清理，防磁盘耗尽）

[POS]
会话暂存管理。GUI-First 架构下 /preview 提取大量二进制文件，直接走 JSON 会导致前端 OOM 或带宽爆炸，
故本模块负责临时落盘；与路由层（HTTP 语义）和落盘执行器（batch_import_execute）解耦。
"""

from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path

from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
    HermesImportedSkill,
)

logger = logging.getLogger(__name__)


class SkillStagingManager:
    """管理批量导入技能时的持久化暂存区 (Persistent Staging Area)。

    在 GUI-First 架构中，/preview 提取了大量的二进制文件（如 Python 脚本）。
    如果不落盘直接通过 JSON 传给前端，会导致前端 OOM 或网络带宽爆炸。
    因此在 /preview 阶段，将完整解析的技能列表序列化存入本暂存区；
    在 /confirm 阶段，再反序列化还原，提取出文件进行最终写盘。
    """

    def __init__(self, base_dir: Path):
        self.staging_dir = base_dir / "staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup_expired_sessions_sync(self) -> None:
        """后台清理超过 24 小时的无主暂存文件，防止磁盘被恶意耗尽"""
        import time

        now = time.time()
        try:
            for f in self.staging_dir.glob("*.pkl"):
                if f.is_file() and now - f.stat().st_mtime > 86400:
                    try:
                        f.unlink()
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Failed to cleanup expired staging sessions: {e}")

    def save_session(
        self, session_id: str, skills: list[HermesImportedSkill]
    ) -> None:
        """持久化保存会话的所有完整技能数据"""
        file_path = self._get_session_path(session_id)
        try:
            with open(file_path, "wb") as f:
                pickle.dump(skills, f)
        except Exception as e:
            logger.error(f"Failed to save staging session {session_id}: {e}")
            raise RuntimeError("暂存区写入失败，请检查磁盘空间或权限。") from e

    def load_session(self, session_id: str) -> list[HermesImportedSkill]:
        """加载暂存会话数据"""
        file_path = self._get_session_path(session_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found in staging area.")

        try:
            with open(file_path, "rb") as f:
                skills = pickle.load(f)  # noqa: S301
            return skills
        except Exception as e:
            logger.error(f"Failed to load staging session {session_id}: {e}")
            raise RuntimeError("暂存区读取失败，会话可能已损坏。") from e

    def cleanup_session(self, session_id: str) -> None:
        """清理已完成的会话，防止垃圾堆积"""
        file_path = self._get_session_path(session_id)
        if file_path.exists():
            try:
                os.remove(file_path)
            except OSError as e:
                logger.warning(f"Failed to cleanup staging file {file_path}: {e}")

    def _get_session_path(self, session_id: str) -> Path:
        # Prevent path traversal
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.staging_dir / f"{safe_id}.pkl"
