"""本地执行态向云沙箱移交的状态机与委派信封打包。

[INPUT]
- 标准库 hashlib / json / time / dataclasses / enum (POS: 完整性指纹、信封载荷与状态枚举)

[OUTPUT]
- DelegationState: local_active → packaging → delegated_to_cloud → resuming_in_cloud →
  completed_awaiting_pullback → restored_to_local
- DelegationEnvelope: 会话与任务标识、DAG 检查点、环境清单、工作区增量与 SHA-256 完整性指纹
- PreflightCheckResult: 云沙箱接力前的预检结果
- DEFAULT_EXCLUDE_PATTERNS: 打包时排除的目录与缓存（`.git`、`node_modules`、`venv` 等）
- WorkloadHandoverDelegator: 打包信封、委派给云沙箱、预检、云端接管、标记云端完成、标记已回到本地

[POS]
移交只带代码与检查点，不带体积巨大的缓存目录；每一步状态转移集中在这一个类里。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

logger = logging.getLogger(__name__)

# 打包工作区增量时必须严格忽略的噪声与巨型缓存目录
DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
)


class DelegationState(StrEnum):
    """双核委派生命周期状态机枚举。"""

    LOCAL_ACTIVE = "local_active"
    PACKAGING = "packaging"
    DELEGATED_TO_CLOUD = "delegated_to_cloud"
    RESUMING_IN_CLOUD = "resuming_in_cloud"
    COMPLETED_AWAITING_PULLBACK = "completed_awaiting_pullback"
    RESTORED_TO_LOCAL = "restored_to_local"


@dataclass(frozen=True, slots=True)
class PreflightCheckResult:
    """云端沙箱接力前的微秒级预检结果。"""

    is_ready: bool
    missing_dependencies: tuple[str, ...] = ()
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class DelegationEnvelope:
    """双核算力委派加密传输信封载荷。"""

    session_id: str
    task_id: str
    current_step: int
    dag_checkpoint: Mapping[str, str]
    env_manifest: Mapping[str, str]
    workspace_patch: Mapping[str, str]
    created_at: float
    checksum: str
    metadata: Mapping[str, str] = field(default_factory=dict)


class WorkloadHandoverDelegator:
    """双核算力委派调度器：管理桌面端本地状态向云沙箱的平滑移交。"""

    def __init__(self, session_id: str, task_id: str) -> None:
        self.session_id = session_id
        self.task_id = task_id
        self._state: DelegationState = DelegationState.LOCAL_ACTIVE
        self._current_envelope: DelegationEnvelope | None = None
        self._cloud_sandbox_id: str | None = None

    @property
    def state(self) -> DelegationState:
        """当前委派状态。"""
        return self._state

    @property
    def current_envelope(self) -> DelegationEnvelope | None:
        """当前生成的委派信封。"""
        return self._current_envelope

    @property
    def cloud_sandbox_id(self) -> str | None:
        """已分配接力的云沙箱实例 ID。"""
        return self._cloud_sandbox_id

    def package_delegation_envelope(
        self,
        current_step: int,
        dag_checkpoint: Mapping[str, str],
        env_manifest: Mapping[str, str],
        raw_files: Mapping[str, str],
        metadata: Mapping[str, str] | None = None,
    ) -> DelegationEnvelope:
        """从当前本地执行态生成轻量化打包信封，过滤所有非代码冗余。"""
        self._state = DelegationState.PACKAGING

        # 1. 过滤忽略的路径（如 node_modules, .git, venv 等）
        filtered_patch: dict[str, str] = {}
        for path, content in raw_files.items():
            normalized = path.replace("\\", "/")
            if any(part in normalized.split("/") for part in DEFAULT_EXCLUDE_PATTERNS):
                continue
            filtered_patch[path] = content

        created_at = time.time()
        # 2. 计算 SHA256 完整性指纹
        hasher = hashlib.sha256()
        hasher.update(self.session_id.encode("utf-8"))
        hasher.update(self.task_id.encode("utf-8"))
        hasher.update(str(current_step).encode("utf-8"))
        hasher.update(json.dumps(dict(dag_checkpoint), sort_keys=True).encode("utf-8"))
        hasher.update(json.dumps(dict(filtered_patch), sort_keys=True).encode("utf-8"))
        checksum = hasher.hexdigest()

        envelope = DelegationEnvelope(
            session_id=self.session_id,
            task_id=self.task_id,
            current_step=current_step,
            dag_checkpoint=dict(dag_checkpoint),
            env_manifest=dict(env_manifest),
            workspace_patch=filtered_patch,
            created_at=created_at,
            checksum=checksum,
            metadata=dict(metadata or {}),
        )
        self._current_envelope = envelope
        return envelope

    def delegate_to_cloud_sandbox(self, target_sandbox_id: str) -> bool:
        """正式将任务委派至指定云沙箱，本地出让执行权。"""
        if self._current_envelope is None:
            logger.error("Cannot delegate to cloud without a packaged envelope.")
            return False

        self._cloud_sandbox_id = target_sandbox_id
        self._state = DelegationState.DELEGATED_TO_CLOUD
        logger.info(
            "Task %s delegated to cloud sandbox %s. Local workspace enters read-only observation mode.",
            self.task_id,
            target_sandbox_id,
        )
        return True

    @staticmethod
    def preflight_cloud_environment(
        envelope: DelegationEnvelope,
        cloud_available_tools: set[str],
    ) -> PreflightCheckResult:
        """在云沙箱接力激活前执行微秒级 Preflight 预检。"""
        required_tools_str = envelope.env_manifest.get("required_tools", "")
        if not required_tools_str:
            return PreflightCheckResult(is_ready=True)

        required_tools = {t.strip() for t in required_tools_str.split(",") if t.strip()}
        missing = required_tools - cloud_available_tools
        if missing:
            return PreflightCheckResult(
                is_ready=False,
                missing_dependencies=tuple(sorted(missing)),
                error_message=f"Cloud sandbox missing required capabilities: {sorted(missing)}",
            )
        return PreflightCheckResult(is_ready=True)

    def activate_cloud_takeover(
        self,
        cloud_available_tools: set[str],
    ) -> bool:
        """云端沙箱原子接管并开始恢复执行。"""
        if self._current_envelope is None or self._state != DelegationState.DELEGATED_TO_CLOUD:
            return False

        check = self.preflight_cloud_environment(self._current_envelope, cloud_available_tools)
        if not check.is_ready:
            logger.error("Cloud takeover rejected: %s", check.error_message)
            return False

        self._state = DelegationState.RESUMING_IN_CLOUD
        logger.info("Cloud takeover active: resumed task %s from step %d.", self.task_id, self._current_envelope.current_step)
        return True

    def mark_cloud_execution_finished(self) -> None:
        """云端沙箱任务执行完毕，等待本地回拉同步。"""
        self._state = DelegationState.COMPLETED_AWAITING_PULLBACK

    def mark_restored_to_local(self) -> None:
        """成果已安全回拉并合并入本地工作区，恢复本地掌控。"""
        self._state = DelegationState.RESTORED_TO_LOCAL
        self._current_envelope = None
        self._cloud_sandbox_id = None
