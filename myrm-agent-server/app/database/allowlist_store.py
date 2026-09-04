"""Database-backed allowlist store for HITL approval system."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone

from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry
from sqlalchemy import delete, select, update
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

        Prunes expired time-bound records lazily on load.

        Args:
            user_id: User identifier (ignored in single-user sandbox mode)
        """
        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()

        async with self._session_factory() as session:
            # Clean up expired grants from DB
            await session.execute(
                delete(UserToolAllowlist).where(
                    UserToolAllowlist.expires_at.is_not(None),
                    UserToolAllowlist.expires_at < now_dt,
                )
            )
            await session.commit()

            stmt = select(UserToolAllowlist)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for r in rows:
                print("DEBUG_DB_ROW_IN_LOAD:", r.id, r.permission, r.expires_at, type(r.expires_at), "now_dt:", now_dt)

            entries = []
            for row in rows:
                if row.expires_at is None:
                    row_expires_ts = None
                elif row.expires_at.tzinfo is None:
                    row_expires_ts = row.expires_at.replace(tzinfo=timezone.utc).timestamp()
                else:
                    row_expires_ts = row.expires_at.timestamp()

                if row_expires_ts is not None and row_expires_ts <= now_ts:
                    continue

                entries.append(
                    AllowlistEntry(
                        permission=row.permission,
                        tool_name=_from_db_value(row.tool_name),
                        tool_args_hash=_from_db_value(row.tool_args_hash),
                        command_pattern=_from_db_value(row.command_pattern),
                        agent_id=_from_db_value(getattr(row, "agent_id", None)),
                        created_at=(
                            (row.created_at.replace(tzinfo=timezone.utc).timestamp() if row.created_at.tzinfo is None else row.created_at.timestamp())
                            if row.created_at
                            else now_ts
                        ),
                        expires_at=row_expires_ts,
                    )
                )
            logger.info(
                "[DB_ALLOWLIST] Loaded %d allowlist entries for user %s",
                len(entries),
                user_id,
            )
            return entries

    async def save(self, user_id: str, entry: AllowlistEntry) -> None:
        """Save allowlist entry to database.

        Args:
            user_id: User identifier
            entry: Allowlist entry to persist
        """
        expires_dt = (
            datetime.fromtimestamp(entry.expires_at, tz=timezone.utc)
            if entry.expires_at is not None
            else None
        )

        async with self._session_factory() as session:
            new_entry = UserToolAllowlist(
                id=uuid.uuid4().hex,
                permission=entry.permission,
                tool_name=_to_db_value(entry.tool_name),
                tool_args_hash=_to_db_value(entry.tool_args_hash),
                command_pattern=_to_db_value(entry.command_pattern),
                agent_id=_to_db_value(entry.agent_id),
                expires_at=expires_dt,
            )
            session.add(new_entry)

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info(
                    "[DB_ALLOWLIST] Entry already exists: (%s, tool=%s, args_hash=%s, pattern=%s, agent=%s)",
                    entry.permission,
                    entry.tool_name,
                    entry.tool_args_hash,
                    entry.command_pattern,
                    entry.agent_id,
                )
                if expires_dt is not None:
                    await session.execute(
                        update(UserToolAllowlist)
                        .where(
                            UserToolAllowlist.permission == entry.permission,
                            UserToolAllowlist.tool_name
                            == _to_db_value(entry.tool_name),
                            UserToolAllowlist.tool_args_hash
                            == _to_db_value(entry.tool_args_hash),
                            UserToolAllowlist.command_pattern
                            == _to_db_value(entry.command_pattern),
                            UserToolAllowlist.agent_id
                            == _to_db_value(entry.agent_id),
                        )
                        .values(expires_at=expires_dt)
                    )
                    await session.commit()
                return
            logger.info(
                "[DB_ALLOWLIST] Saved (%s, tool=%s, args_hash=%s, pattern=%s, agent=%s)",
                entry.permission,
                entry.tool_name,
                entry.tool_args_hash,
                entry.command_pattern,
                entry.agent_id,
            )

    async def remove(
        self,
        user_id: str,
        permission: str,
        tool_name: str | None = None,
        tool_args_hash: str | None = None,
        command_pattern: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Remove allowlist entry from database.

        Args:
            user_id: User identifier (unused in query, reserved for multi-tenant)
            permission: Permission type
            tool_name: Optional tool name (None for permission-level removal)
            tool_args_hash: Optional args hash (None for tool-level removal)
            command_pattern: Optional shell glob pattern (None for non-pattern removal)
            agent_id: Optional agent identity scope
        """
        async with self._session_factory() as session:
            stmt = select(UserToolAllowlist).where(
                UserToolAllowlist.permission == permission,
                UserToolAllowlist.tool_name == _to_db_value(tool_name),
                UserToolAllowlist.tool_args_hash == _to_db_value(tool_args_hash),
                UserToolAllowlist.command_pattern == _to_db_value(command_pattern),
                UserToolAllowlist.agent_id == _to_db_value(agent_id),
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()

            if entry:
                await session.delete(entry)
                await session.commit()
                logger.info(
                    "[DB_ALLOWLIST] Removed (%s, tool=%s, args_hash=%s, pattern=%s, agent=%s)",
                    permission,
                    tool_name,
                    tool_args_hash,
                    command_pattern,
                    agent_id,
                )
            else:
                logger.info(
                    "[DB_ALLOWLIST] Entry not found for removal: permission=%s tool=%s args_hash=%s pattern=%s agent=%s",
                    permission,
                    tool_name,
                    tool_args_hash,
                    command_pattern,
                    agent_id,
                )
