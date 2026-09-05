"""Unit tests for DBAllowlistStore database persistence with agent_id scope."""

from __future__ import annotations

import asyncio
import time

import pytest
from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry

from app.database.allowlist_store import DBAllowlistStore
from app.database.connection import init_database
from app.platform_utils import get_session_factory
from tests.support.allowlist_test_seed import clear_allowlist_entries


@pytest.fixture(autouse=True)
def _setup_db():
    asyncio.run(init_database())
    asyncio.run(clear_allowlist_entries())
    yield
    asyncio.run(clear_allowlist_entries())


class TestDBAllowlistStore:
    @pytest.mark.asyncio
    async def test_save_and_load_with_agent_scope(self):
        factory = get_session_factory()
        store = DBAllowlistStore(factory)
        user_id = "sandbox"

        entry = AllowlistEntry(
            permission="mcp_invoke",
            tool_name="mcp__github__create_issue",
            tool_args_hash=None,
            command_pattern=None,
            agent_id="code_assistant_subagent",
        )

        await store.save(user_id, entry)

        entries = await store.load(user_id)
        assert len(entries) == 1
        loaded = entries[0]
        assert loaded.permission == "mcp_invoke"
        assert loaded.tool_name == "mcp__github__create_issue"
        assert loaded.agent_id == "code_assistant_subagent"

    @pytest.mark.asyncio
    async def test_remove_with_agent_scope(self):
        factory = get_session_factory()
        store = DBAllowlistStore(factory)
        user_id = "sandbox"

        entry_a = AllowlistEntry(
            permission="mcp_invoke",
            tool_name="mcp__github__create_issue",
            agent_id="agent_a",
        )
        entry_b = AllowlistEntry(
            permission="mcp_invoke",
            tool_name="mcp__github__create_issue",
            agent_id="agent_b",
        )

        await store.save(user_id, entry_a)
        await store.save(user_id, entry_b)

        entries = await store.load(user_id)
        assert len(entries) == 2

        # Remove only agent_a
        await store.remove(
            user_id,
            permission="mcp_invoke",
            tool_name="mcp__github__create_issue",
            agent_id="agent_a",
        )

        remaining = await store.load(user_id)
        assert len(remaining) == 1
        assert remaining[0].agent_id == "agent_b"

    @pytest.mark.asyncio
    async def test_save_and_load_with_expires_at(self):

        await clear_allowlist_entries()
        factory = get_session_factory()
        store = DBAllowlistStore(factory)
        user_id = "sandbox"
        future_ts = time.time() + 3600.0

        entry = AllowlistEntry(
            permission="shell_exec",
            tool_name="bash",
            expires_at=future_ts,
        )

        await store.save(user_id, entry)

        entries = await store.load(user_id)
        assert len(entries) == 1
        assert entries[0].expires_at is not None
        assert abs(entries[0].expires_at - future_ts) < 2.0

    @pytest.mark.asyncio
    async def test_expired_entry_auto_cleanup(self):
        factory = get_session_factory()
        store = DBAllowlistStore(factory)
        user_id = "sandbox"
        past_ts = time.time() - 3600.0

        entry = AllowlistEntry(
            permission="shell_exec",
            tool_name="bash",
            expires_at=past_ts,
        )

        await store.save(user_id, entry)

        entries = await store.load(user_id)
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_update_expires_at_on_duplicate_save(self):
        factory = get_session_factory()
        store = DBAllowlistStore(factory)
        user_id = "sandbox"
        t1 = time.time() + 1000.0
        t2 = time.time() + 3600.0

        entry1 = AllowlistEntry(
            permission="shell_exec",
            tool_name="bash",
            expires_at=t1,
        )
        await store.save(user_id, entry1)

        entry2 = AllowlistEntry(
            permission="shell_exec",
            tool_name="bash",
            expires_at=t2,
        )
        await store.save(user_id, entry2)

        entries = await store.load(user_id)
        assert len(entries) == 1
        assert entries[0].expires_at is not None
        assert abs(entries[0].expires_at - t2) < 2.0

    @pytest.mark.asyncio
    async def test_session_scoped_entry_skipped_from_db_persistence(self):
        """Ensure that entries with session_id set are never written to database."""
        factory = get_session_factory()
        store = DBAllowlistStore(factory)
        user_id = "sandbox"

        session_entry = AllowlistEntry(
            permission="shell_exec",
            tool_name="bash",
            session_id="session_do_not_persist_123",
        )
        await store.save(user_id, session_entry)

        entries = await store.load(user_id)
        assert len(entries) == 0

