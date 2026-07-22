"""Allowlist management API endpoints.

[INPUT]
- app.database.models::UserToolAllowlist (POS: 安全 allowlist ORM)
- app.api.security.allowlist_granularity (POS: REST 粒度映射)
- myrm_agent_harness.agent.security::get_allowlist (POS: harness 持久 allowlist)

[OUTPUT]
- GET/DELETE /api/v1/security/allowlist: list/delete allow-always records

[POS]
Settings「允许记录」REST 入口。返回 command_pattern 与正确 granularity，delete 同步 harness 缓存。
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security.allowlist_granularity import nullable_db_field, resolve_allowlist_granularity
from app.api.security.test_fixtures import router as allowlist_test_fixtures_router
from app.core.utils.errors import not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import UserToolAllowlist

router = APIRouter()


@router.get("")
async def list_allowlist_entries(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """List all allowlist entries for the current user."""
    stmt = select(UserToolAllowlist).order_by(UserToolAllowlist.created_at.desc())
    result = await db.execute(stmt)
    entries = result.scalars().all()

    data = [
        {
            "id": entry.id,
            "permission": entry.permission,
            "tool_name": nullable_db_field(entry.tool_name),
            "tool_args_hash": nullable_db_field(entry.tool_args_hash),
            "command_pattern": nullable_db_field(entry.command_pattern),
            "created_at": entry.created_at.isoformat(),
            "granularity": resolve_allowlist_granularity(
                tool_name=entry.tool_name,
                tool_args_hash=entry.tool_args_hash,
                command_pattern=entry.command_pattern,
            ),
        }
        for entry in entries
    ]

    return success_response(data=data)


@router.delete("/{entry_id}")
async def delete_allowlist_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete a specific allowlist entry."""
    stmt = select(UserToolAllowlist).where(UserToolAllowlist.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    if not entry:
        raise not_found_error("Allowlist entry")

    await db.delete(entry)
    await db.commit()

    from myrm_agent_harness.agent.security.approval_flow import get_allowlist

    allowlist = get_allowlist()
    await allowlist.remove(
        user_id="sandbox",
        permission=entry.permission,
        tool_name=nullable_db_field(entry.tool_name),
        tool_args_hash=nullable_db_field(entry.tool_args_hash),
        command_pattern=nullable_db_field(entry.command_pattern),
    )

    return success_response(data={"deleted": True})


@router.delete("")
async def clear_all_allowlist_entries(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete all allowlist entries for the current user."""
    count_stmt = select(func.count()).select_from(UserToolAllowlist)
    count_result = await db.execute(count_stmt)
    count_val = count_result.scalar_one()
    count = int(count_val) if isinstance(count_val, int) else 0

    await db.execute(delete(UserToolAllowlist))
    await db.commit()

    from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID, get_allowlist

    await get_allowlist().clear_user(DEFAULT_USER_ID)

    return success_response(data={"count": count})

router.include_router(allowlist_test_fixtures_router)
