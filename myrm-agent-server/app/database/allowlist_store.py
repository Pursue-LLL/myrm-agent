"""Database-backed allowlist store for HITL approval system."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager

from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserToolAllowlist

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

logger = logging.getLogger(__name__)

_NULL_SENTINEL = ""


def _to_db_value(value: str | None) -> str:
    """Convert None to empty string for database storage."""
    return _NULL_SENTINEL if value is None else value


def _from_db_value(value: str) -> str | None:
    """Convert empty string back to None from database."""
    return None if value == _NULL_SENTINEL else value


class DBAllowlistStore:
    """Database-persisted allowlist store.

    Implements AllowlistStore Protocol for persisting user "always allow" rules.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def load(self, user_id: str) -> Sequence[AllowlistEntry]:
        """Load allowlist entries from database.

        Args:
            user_id: User identifier (ignored in single-user sandbox mode)
        """
        async with self._session_factory() as session:
            stmt = select(UserToolAllowlist)
            result = await session.execute(stmt)
            rows = result.scalars().all()

            entries = [
                AllowlistEntry(
                    permission=row.permission,
                    tool_name=_from_db_value(row.tool_name),
                    tool_args_hash=_from_db_value(row.tool_args_hash),
                    command_pattern=_from_db_value(row.command_pattern),
                    created_at=row.created_at.timestamp(),
                )
                for row in rows
            ]
            logger.info("[DB_ALLOWLIST] Loaded %d allowlist entries for user %s", len(entries), user_id)
            return entries

    async def save(self, user_id: str, entry: AllowlistEntry) -> None:
        """Save allowlist entry to database.

        Args:
            user_id: User identifier
            entry: Allowlist entry to persist
        """
        async with self._session_factory() as session:
            new_entry = UserToolAllowlist(
                id=uuid.uuid4().hex,
                permission=entry.permission,
                tool_name=_to_db_value(entry.tool_name),
                tool_args_hash=_to_db_value(entry.tool_args_hash),
                command_pattern=_to_db_value(entry.command_pattern),
            )
            session.add(new_entry)

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info(
                    "[DB_ALLOWLIST] Entry already exists: (%s, tool=%s, args_hash=%s, pattern=%s)",
                    entry.permission,
                    entry.tool_name,
                    entry.tool_args_hash,
                    entry.command_pattern,
                )
                return
            logger.info(
                "[DB_ALLOWLIST] Saved (%s, tool=%s, args_hash=%s, pattern=%s)",
                entry.permission,
                entry.tool_name,
                entry.tool_args_hash,
                entry.command_pattern,
            )

    async def remove(
        self,
        user_id: str,
        permission: str,
        tool_name: str | None = None,
        tool_args_hash: str | None = None,
        command_pattern: str | None = None,
    ) -> None:
        """Remove allowlist entry from database.

        Args:
            user_id: User identifier (unused in query, reserved for multi-tenant)
            permission: Permission type
            tool_name: Optional tool name (None for permission-level removal)
            tool_args_hash: Optional args hash (None for tool-level removal)
            command_pattern: Optional shell glob pattern (None for non-pattern removal)
        """
        async with self._session_factory() as session:
            stmt = select(UserToolAllowlist).where(
                UserToolAllowlist.permission == permission,
                UserToolAllowlist.tool_name == _to_db_value(tool_name),
                UserToolAllowlist.tool_args_hash == _to_db_value(tool_args_hash),
                UserToolAllowlist.command_pattern == _to_db_value(command_pattern),
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()

            if entry:
                await session.delete(entry)
                await session.commit()
                logger.info(
                    "[DB_ALLOWLIST] Removed (%s, tool=%s, args_hash=%s, pattern=%s)",
                    permission,
                    tool_name,
                    tool_args_hash,
                    command_pattern,
                )
            else:
                logger.info(
                    "[DB_ALLOWLIST] Entry not found for removal: permission=%s tool=%s args_hash=%s pattern=%s",
                    permission,
                    tool_name,
                    tool_args_hash,
                    command_pattern,
                )
