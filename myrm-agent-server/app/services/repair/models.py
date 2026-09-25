"""[INPUT]
- pydantic::BaseModel, Field (POS: 数据校验与模型定义标准库)

[OUTPUT]
- RepairActionId: 已知修复动作枚举
- RepairRiskLevel: 修复动作风险等级
- RepairScope: 修复作用域
- RepairAction: 白名单可审计修复动作结构
- RepairActionExecuteRequest: 修复执行请求
- RepairActionExecuteResult: 修复执行结果

[POS]
Server 业务层运行时修复动作数据契约与模型定义。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RepairActionId(StrEnum):
    """Known repair actions exposed to GUI clients."""

    CLEANUP_BROWSER_ORPHANS = "cleanup_browser_orphans"
    REVIEW_CHANNEL_DLQ = "review_channel_dlq"
    REVIEW_WORKSPACE_STORAGE = "review_workspace_storage"
    REVIEW_RUNTIME_DEPENDENCY = "review_runtime_dependency"
    SQLITE_BACKUP_NOW = "sqlite_backup_now"
    SQLITE_RESTORE_LATEST = "sqlite_restore_latest"
    PURGE_ORPHAN_SESSIONS = "purge_orphan_sessions"


class RepairRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RepairScope(StrEnum):
    CURRENT_RUNTIME = "current_runtime"
    CURRENT_WORKSPACE = "current_workspace"
    INTEGRATION = "integration"
    PLATFORM_SANDBOX = "platform_sandbox"


class RepairAction(BaseModel):
    """A GUI-safe, auditable repair recommendation."""

    action_id: RepairActionId
    title: str
    description: str
    component: str
    layer: str
    scope: RepairScope
    risk_level: RepairRiskLevel
    requires_approval: bool = True
    dry_run_supported: bool = True
    executable: bool
    method: str | None = None
    endpoint: str | None = None
    confirm_required: bool = True
    reason: str
    expected_effect: str
    does_not_do: list[str] = Field(default_factory=list)


class RepairActionExecuteRequest(BaseModel):
    """Execution request for a white-listed repair action."""

    dry_run: bool = Field(default=True, description="Preview the action without changing runtime state.")
    confirm: bool = Field(default=False, description="Required for state-changing execution.")


class RepairActionExecuteResult(BaseModel):
    """Execution result for a white-listed repair action."""

    action_id: RepairActionId
    status: str
    changed: bool
    dry_run: bool
    message: str
    details: dict[str, object] = Field(default_factory=dict)
