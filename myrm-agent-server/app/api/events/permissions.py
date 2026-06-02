"""Permission Management API (local mode only).

Features:
- Permission approval: one-time and always-allow decisions
- Security mode switching: Safe/Ask/Allow All (persisted to local file)
- Allowlist management: query, delete always-allow rules
- Permission checking: uses framework evaluate_tool_call
- Audit logging: structured logs for all permission decisions

Architecture:
- Framework: SecurityConfig + ApprovalFlow + AllowlistStore
- Business: API glue + LOCAL_USER_ID + persistence
- Storage: SQLite (DBAllowlistStore) + local file (permission_mode.txt)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry, get_allowlist
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.types import (
    DEFAULT_CAPABILITIES,
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    PermissionRuleset,
    SecurityConfig,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.config.deploy_mode import is_local_mode

logger = logging.getLogger(__name__)

# Local mode user ID (single-user environment)
LOCAL_USER_ID = "sandbox"

# Persistence config
_PERMISSION_MODE_FILE = Path.home() / ".myrm" / "permission_mode.txt"

router = APIRouter(prefix="/permissions")

# ============================================================================
# Security Config Management (framework-layer based)
# ============================================================================


class SecurityMode:
    """安全模式映射：将简化的mode概念映射到框架层的完整SecurityConfig"""

    SAFE = "safe"
    ASK = "ask"
    ALLOW_ALL = "allow_all"


def _build_security_config_for_mode(mode: str) -> SecurityConfig:
    """根据模式构建SecurityConfig

    - safe: 只允许只读和安全操作
    - ask: 危险操作需要审批
    - allow_all: 信任所有操作
    """
    if mode == SecurityMode.ALLOW_ALL:
        ruleset: PermissionRuleset = (PermissionRule("*", "*", PermissionAction.ALLOW),)
    elif mode == SecurityMode.SAFE:
        ruleset = (
            PermissionRule("file_read", "*", PermissionAction.ALLOW),
            PermissionRule("list_directory", "*", PermissionAction.ALLOW),
            PermissionRule("search_files", "*", PermissionAction.ALLOW),
            PermissionRule("get_file_info", "*", PermissionAction.ALLOW),
            PermissionRule("web_search", "*", PermissionAction.ALLOW),
            PermissionRule("shell_exec", "*", PermissionAction.DENY),
            PermissionRule("code_interpreter", "*", PermissionAction.DENY),
            PermissionRule("file_write", "*", PermissionAction.DENY),
            PermissionRule("browser_navigate_tool", "*", PermissionAction.DENY),
            PermissionRule("*", "*", PermissionAction.DENY),
        )
    else:
        ruleset = DEFAULT_RULESET

    return SecurityConfig(
        capabilities=DEFAULT_CAPABILITIES,
        ruleset=ruleset,
        approval_timeout_seconds=120,
        approval_timeout_behavior="deny",
    )


def _load_persisted_mode() -> str:
    """从持久化文件加载security mode"""
    try:
        if _PERMISSION_MODE_FILE.exists():
            mode = _PERMISSION_MODE_FILE.read_text().strip()
            if mode in (SecurityMode.SAFE, SecurityMode.ASK, SecurityMode.ALLOW_ALL):
                logger.info(f"Loaded persisted permission mode: {mode}")
                return mode
    except Exception as e:
        logger.warning(f"Failed to load persisted permission mode: {e}")
    return SecurityMode.ASK  # Default


def _persist_mode(mode: str) -> None:
    """持久化security mode到文件"""
    try:
        _PERMISSION_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PERMISSION_MODE_FILE.write_text(mode)
        logger.info(f"Persisted permission mode: {mode}")
    except Exception as e:
        logger.error(f"Failed to persist permission mode: {e}")


# Initialize from persisted state
_current_mode = _load_persisted_mode()
_security_config: SecurityConfig = _build_security_config_for_mode(_current_mode)


def get_current_security_config() -> SecurityConfig:
    """获取当前的SecurityConfig"""
    return _security_config


def set_security_mode(mode: str) -> None:
    """设置安全模式，更新全局SecurityConfig并持久化"""
    global _current_mode, _security_config
    _current_mode = mode
    _security_config = _build_security_config_for_mode(mode)
    _persist_mode(mode)  # Persist to file
    logger.info("Security mode updated to: %s", mode)


# ============================================================================
# In-memory pending requests store (for real-time approval flow)
# ============================================================================

# 存储待审批的权限请求 {request_id: PendingRequest}
_pending_requests: dict[str, "PendingRequest"] = {}

# 存储审批结果的 Future {request_id: asyncio.Future}
_approval_futures: dict[str, asyncio.Future[bool]] = {}


class PendingRequest(BaseModel):
    """待审批的权限请求"""

    id: str
    turn_id: str | None = None
    action: str
    resource: str
    details: dict[str, object] = Field(default_factory=dict)
    risk_level: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Schemas
# ============================================================================


class PermissionCheckRequest(BaseModel):
    """权限检查请求"""

    action: str = Field(..., description="操作类型: tool_call/command/file_write/file_delete")
    resource: str = Field(..., description="资源标识")
    details: dict[str, object] = Field(default_factory=dict, description="额外信息")
    turn_id: str | None = Field(None, description="关联的 Turn ID")


class PermissionCheckResponse(BaseModel):
    """权限检查响应"""

    decision: str  # allow / deny / ask
    risk_level: str
    reason: str
    request_id: str | None = None  # 如果需要审批，返回 request_id


class PermissionApprovalRequest(BaseModel):
    """权限审批请求"""

    approved: bool
    always_allow: bool = Field(default=False, description="是否永久允许（添加到白名单）")
    reason: str | None = None


class PermissionApprovalResponse(BaseModel):
    """权限审批响应"""

    success: bool
    message: str


class PendingRequestList(BaseModel):
    """待审批请求列表"""

    requests: list[PendingRequest]


class PolicyModeRequest(BaseModel):
    """策略模式设置请求"""

    mode: str = Field(..., description="权限模式: safe/ask/allow_all")


class PolicyModeResponse(BaseModel):
    """策略模式响应"""

    mode: str
    description: str


class AllowlistEntryResponse(BaseModel):
    """白名单条目响应"""

    permission: str
    tool_name: str | None = None
    tool_args_hash: str | None = None
    created_at: float


class AllowlistResponse(BaseModel):
    """白名单列表响应"""

    entries: list[AllowlistEntryResponse]


# ============================================================================
# Helper
# ============================================================================


def require_local_mode() -> None:
    """检查是否为本地模式"""
    if not is_local_mode():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This feature is only available in local mode",
        )


# ============================================================================
# Routes
# ============================================================================


@router.post("/check", response_model=PermissionCheckResponse)
async def check_permission(
    request: PermissionCheckRequest,
    db: AsyncSession = Depends(get_db_session),
) -> PermissionCheckResponse:
    """检查操作权限

    使用框架层6层安全架构评估权限。
    如果返回 decision=ask，前端需要展示审批对话框。
    """
    require_local_mode()

    config = get_current_security_config()

    permission_type = _action_to_permission(request.action)

    tool_input = {**request.details}
    if request.action == "tool_call":
        tool_input["command"] = request.resource
    elif request.action == "command":
        tool_input["command"] = request.resource
    elif request.action in ("file_write", "file_delete"):
        tool_input["path"] = request.resource

    try:
        action, reason = evaluate_tool_call(
            permission=permission_type,
            tool_input=tool_input,
            config=config,
        )
        risk_level = _infer_risk_level(permission_type, action)

        response = PermissionCheckResponse(
            decision=action.value,
            risk_level=risk_level,
            reason=reason or f"Permission {action.value}",
        )

        # Audit log: record permission decision
        logger.info(
            "Permission decision",
            extra={
                "event_type": "permission_decision",
                "action": request.action,
                "resource": request.resource,
                "permission_type": permission_type,
                "decision": action.value,
                "risk_level": risk_level,
                "reason": reason,
                "turn_id": request.turn_id,
                "details": request.details,
            },
        )
    except Exception as e:
        logger.error(f"Permission evaluation failed for {permission_type}: {e}", exc_info=True)
        # Fail-closed: deny by default on evaluation error
        response = PermissionCheckResponse(
            decision="deny",
            risk_level="critical",
            reason=f"Evaluation error: {str(e)}",
        )

        # Audit log: record error
        logger.warning(
            "Permission evaluation error",
            extra={
                "event_type": "permission_error",
                "action": request.action,
                "resource": request.resource,
                "permission_type": permission_type,
                "error": str(e),
                "turn_id": request.turn_id,
            },
        )
        return response

    if action == PermissionAction.ASK:
        request_id = str(uuid.uuid4())
        pending = PendingRequest(
            id=request_id,
            turn_id=request.turn_id,
            action=request.action,
            resource=request.resource,
            details=request.details,
            risk_level=risk_level,
            reason=reason or "Requires user approval",
        )
        _pending_requests[request_id] = pending
        response.request_id = request_id

    return response


def _action_to_permission(action: str) -> str:
    """将API的action类型映射到框架层的permission类型"""
    mapping = {
        "tool_call": "shell_exec",  # 通用工具调用
        "command": "shell_exec",
        "file_write": "file_write",
        "file_delete": "file_write",  # 删除也算写操作
    }
    return mapping.get(action, action)


def _infer_risk_level(permission: str, action: PermissionAction) -> str:
    """推断风险等级"""
    if action == PermissionAction.DENY:
        return "critical"
    elif action == PermissionAction.ASK:
        if permission in ("shell_exec", "code_interpreter"):
            return "high"
        return "medium"
    return "low"


@router.get("/pending", response_model=PendingRequestList)
async def get_pending_requests() -> PendingRequestList:
    """获取所有待审批的权限请求"""
    require_local_mode()

    return PendingRequestList(requests=list(_pending_requests.values()))


@router.get("/pending/{request_id}", response_model=PendingRequest)
async def get_pending_request(request_id: str) -> PendingRequest:
    """获取单个待审批请求"""
    require_local_mode()

    if request_id not in _pending_requests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending request {request_id} not found",
        )

    return _pending_requests[request_id]


@router.post("/pending/{request_id}/approve", response_model=PermissionApprovalResponse)
async def approve_request(
    request_id: str,
    approval: PermissionApprovalRequest,
) -> PermissionApprovalResponse:
    """审批权限请求

    前端用户点击"允许"或"拒绝"后调用此接口。
    支持 "Always Allow" 功能，将规则保存到持久化白名单。
    """
    require_local_mode()

    if request_id not in _pending_requests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending request {request_id} not found",
        )

    pending = _pending_requests.pop(request_id)

    # If user clicks "Always Allow", add to persistent allowlist
    if approval.approved and approval.always_allow:
        try:
            permission_type = _action_to_permission(pending.action)
            entry = AllowlistEntry(
                permission=permission_type,
                tool_name=None,  # Permission-level match (all tools of this type)
                tool_args_hash=None,
            )
            allowlist = get_allowlist()
            await allowlist.add(LOCAL_USER_ID, entry)
            logger.info(f"Added to allowlist: permission={permission_type}, user={LOCAL_USER_ID}")
        except Exception as e:
            logger.error(f"Failed to add to allowlist: {e}", exc_info=True)

    # 如果有等待的 Future，设置结果
    if request_id in _approval_futures:
        future = _approval_futures.pop(request_id)
        if not future.done():
            future.set_result(approval.approved)

    action_desc = "approved" if approval.approved else "denied"
    if approval.always_allow:
        action_desc = "approved (always allow)"

    return PermissionApprovalResponse(
        success=True,
        message=f"Request {request_id} {action_desc}",
    )


@router.delete("/pending/{request_id}", response_model=PermissionApprovalResponse)
async def cancel_pending_request(request_id: str) -> PermissionApprovalResponse:
    """取消待审批请求"""
    require_local_mode()

    if request_id not in _pending_requests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending request {request_id} not found",
        )

    _pending_requests.pop(request_id)

    # 如果有等待的 Future，设置拒绝
    if request_id in _approval_futures:
        future = _approval_futures.pop(request_id)
        if not future.done():
            future.set_result(False)

    return PermissionApprovalResponse(
        success=True,
        message=f"Request {request_id} cancelled",
    )


@router.get("/allowlist", response_model=AllowlistResponse)
async def get_allowlist_entries() -> AllowlistResponse:
    """获取用户的Always Allow白名单

    返回所有已保存的"始终允许"规则
    """
    require_local_mode()

    try:
        allowlist = get_allowlist()
        await allowlist.load_user(LOCAL_USER_ID)

        entries = []
        if LOCAL_USER_ID in allowlist._entries:
            for entry in allowlist._entries[LOCAL_USER_ID].values():
                entries.append(
                    AllowlistEntryResponse(
                        permission=entry.permission,
                        tool_name=entry.tool_name,
                        tool_args_hash=entry.tool_args_hash,
                        created_at=entry.created_at,
                    )
                )

        return AllowlistResponse(entries=entries)
    except Exception as e:
        logger.error(f"Failed to load allowlist: {e}", exc_info=True)
        return AllowlistResponse(entries=[])


@router.delete("/allowlist/{permission}")
async def remove_allowlist_entry(permission: str) -> dict[str, object]:
    """从白名单中删除规则

    Args:
        permission: 权限类型（如 shell_exec, file_write）
    """
    require_local_mode()

    try:
        allowlist = get_allowlist()
        if allowlist._store:
            await allowlist._store.remove(
                user_id=LOCAL_USER_ID,
                permission=permission,
                tool_name=None,
                tool_args_hash=None,
            )

        # Also remove from in-memory cache
        if LOCAL_USER_ID in allowlist._entries:
            key = (permission, None, None)
            allowlist._entries[LOCAL_USER_ID].pop(key, None)

        logger.info(f"Removed from allowlist: permission={permission}, user={LOCAL_USER_ID}")
        return {"success": True, "message": f"Rule for {permission} removed"}
    except Exception as e:
        logger.error(f"Failed to remove from allowlist: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove allowlist entry: {str(e)}",
        ) from e


@router.get("/mode", response_model=PolicyModeResponse)
async def get_policy_mode() -> PolicyModeResponse:
    """获取当前策略模式"""
    require_local_mode()

    descriptions = {
        SecurityMode.SAFE: "Safe mode - Only allows read-only and safe operations",
        SecurityMode.ASK: "Ask mode - Prompts for approval on potentially dangerous operations",
        SecurityMode.ALLOW_ALL: "Allow all mode - Trusts all operations (use with caution)",
    }

    return PolicyModeResponse(
        mode=_current_mode,
        description=descriptions.get(_current_mode, "Unknown mode"),
    )


@router.put("/mode", response_model=PolicyModeResponse)
async def set_policy_mode(request: PolicyModeRequest) -> PolicyModeResponse:
    """设置策略模式

    更新全局SecurityConfig以反映新模式
    """
    require_local_mode()

    valid_modes = {SecurityMode.SAFE, SecurityMode.ASK, SecurityMode.ALLOW_ALL}
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode: {request.mode}. Must be one of: safe, ask, allow_all",
        )

    set_security_mode(request.mode)

    descriptions = {
        SecurityMode.SAFE: "Safe mode - Only allows read-only and safe operations",
        SecurityMode.ASK: "Ask mode - Prompts for approval on potentially dangerous operations",
        SecurityMode.ALLOW_ALL: "Allow all mode - Trusts all operations (use with caution)",
    }

    return PolicyModeResponse(
        mode=_current_mode,
        description=descriptions.get(_current_mode, "Unknown mode"),
    )
