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
