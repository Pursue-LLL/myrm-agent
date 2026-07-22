"""Seed helpers for allowlist API / Chrome E2E tests."""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.database.models import UserToolAllowlist
from app.platform_utils import get_session_factory

PATTERN_ENTRY_PERMISSION = "shell_exec"
PATTERN_ENTRY_TOOL = "bash_code_execute_tool"
PATTERN_ENTRY_COMMAND_PATTERN = "npm install *"


async def clear_allowlist_entries() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(UserToolAllowlist))
        await session.commit()


async def seed_pattern_allowlist_entry() -> str:
    entry_id = uuid.uuid4().hex
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            UserToolAllowlist(
                id=entry_id,
                permission=PATTERN_ENTRY_PERMISSION,
                tool_name=PATTERN_ENTRY_TOOL,
                tool_args_hash="",
                command_pattern=PATTERN_ENTRY_COMMAND_PATTERN,
            ),
        )
        await session.commit()
    return entry_id
