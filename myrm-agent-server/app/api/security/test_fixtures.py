"""Local-only HTTP fixtures for allowlist Chrome E2E.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
myrm_agent_harness.agent.security.approval_flow (POS: AllowlistEntry SSOT)
app.database.models::UserToolAllowlist (POS: allowlist 持久化)

[OUTPUT]
seed_pattern_fixture: 写入 allowlist 命令模式行供 Chrome E2E 断言

[POS]
Security API 本地测试 fixture。为 allowlist pattern Chrome E2E 提供无 LLM 的 DB 种子。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.security.approval_flow import (
    DEFAULT_USER_ID,
    AllowlistEntry,
    get_allowlist,
)
from sqlalchemy import delete, select

from app.config.deploy_mode import is_local_mode
from app.database.models import UserToolAllowlist
from app.platform_utils import get_session_factory

router = APIRouter()

_PATTERN_PERMISSION = "shell_exec"
_PATTERN_TOOL = "bash_code_execute_tool"
_PATTERN_COMMAND = "npm install *"


async def _clear_allowlist_rows() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(UserToolAllowlist))
        await session.commit()


@router.post("/test/seed-pattern-fixture", include_in_schema=False)
async def seed_pattern_allowlist_fixture() -> dict[str, str]:
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    await _clear_allowlist_rows()
    entry = AllowlistEntry(
        permission=_PATTERN_PERMISSION,
        tool_name=_PATTERN_TOOL,
        tool_args_hash=None,
        command_pattern=_PATTERN_COMMAND,
    )
    allowlist = get_allowlist()
    await allowlist.add(DEFAULT_USER_ID, entry)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(UserToolAllowlist).where(
                UserToolAllowlist.command_pattern == _PATTERN_COMMAND,
            ),
        )
        row = result.scalar_one_or_none()
        entry_id = row.id if row is not None else ""

    return {
        "entry_id": entry_id,
        "command_pattern": _PATTERN_COMMAND,
        "tool_name": _PATTERN_TOOL,
    }


@router.delete("/test/clear-pattern-fixture", include_in_schema=False)
async def clear_pattern_allowlist_fixture() -> dict[str, bool]:
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    await _clear_allowlist_rows()
    allowlist = get_allowlist()
    await allowlist.clear_user(DEFAULT_USER_ID)
    return {"cleared": True}


@router.post("/test/reset-hitl-runtime", include_in_schema=False)
async def reset_hitl_runtime_fixture() -> dict[str, bool]:
    """Drop POOLED agent cache + config/allowlist in-memory state for LIVE HITL E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.services.agent.execution_cache import get_execution_cache

    await get_execution_cache().close_all()
    invalidate_user_configs_cache()

    allowlist = get_allowlist()
    await allowlist.clear_user(DEFAULT_USER_ID)
    allowlist._entries.pop(DEFAULT_USER_ID, None)
    allowlist._cache_meta.pop(DEFAULT_USER_ID, None)

    return {"ok": True}


@router.get("/test/hitl-probe", include_in_schema=False)
async def hitl_runtime_probe(
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> dict[str, object]:
    """Return effective shell HITL evaluation for LIVE E2E diagnostics."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
    from myrm_agent_harness.agent.security.engine import evaluate_tool_call
    from myrm_agent_harness.agent.security.types import PermissionAction

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS

    configs = await load_user_configs()
    raw = configs.security_config_dict if configs else None
    agent_raw: dict[str, object] | None = None
    if agent_id:
        from app.services.agent.profile_resolver import AgentProfileResolver

        resolved = await AgentProfileResolver().resolve(agent_id)
        if resolved and resolved.security_overrides:
            agent_raw = dict(resolved.security_overrides)
    sec = build_channel_security_config(
        "web_chat",
        raw,
        agent_security_raw=agent_raw,
        local_mode=True,
    )
    command = "curl -sS http://127.0.0.1:9/ALLOWLIST_LIVE_PROBE"
    action, reason = evaluate_tool_call(
        "shell_exec",
        {"command": command},
        sec,
        tool_name="bash_code_execute_tool",
    )
    collector = ACTIVE_COLLECTORS.get(chat_id) if chat_id else None
    pending_interrupts = collector.has_pending_hitl_replay() if collector is not None else False
    pending_events: list[dict[str, object]] = []
    if collector is not None and pending_interrupts:
        pending_events = [dict(event) for event in collector._pending_interrupt_events]
    return {
        "yolo": sec.yolo_mode_enabled,
        "auto_mode": sec.auto_mode_enabled,
        "action": action.value,
        "reason": reason,
        "permissions": (raw or {}).get("permissions") if isinstance(raw, dict) else None,
        "raw_yolo": (raw or {}).get("yoloModeEnabled") if isinstance(raw, dict) else None,
        "agent_yolo": (agent_raw or {}).get("yoloModeEnabled") if isinstance(agent_raw, dict) else None,
        "agent_id": agent_id,
        "expects_ask": action == PermissionAction.ASK and not sec.yolo_mode_enabled,
        "harness_audit_tail": _harness_audit_tail(),
        "chat_id": chat_id,
        "collector_active": collector is not None,
        "pending_hitl_replay": pending_interrupts,
        "pending_interrupt_events": pending_events,
    }


def _harness_audit_tail(*, limit: int = 12) -> list[dict[str, object]]:
    try:
        from myrm_agent_harness.agent.security.audit import get_audit_entries

        rows = get_audit_entries()
        tail: list[dict[str, object]] = []
        for row in rows[-limit:]:
            if hasattr(row, "to_dict"):
                payload = row.to_dict()
                tail.append(payload if isinstance(payload, dict) else {"value": str(payload)})
            elif isinstance(row, dict):
                tail.append(row)
        return tail
    except Exception:
        return []
