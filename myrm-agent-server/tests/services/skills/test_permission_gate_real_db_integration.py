"""Real-DB integration tests for the skill permission gate chain.

Runs the full production wiring with real database persistence — no mocks:
grant rows inserted into SQLite → ``load_granted_permissions_cached`` reads the
DB through the per-session cache → ``create_async_permission_checker`` →
``SkillBoundaryProvider`` inside ``GuardrailMiddleware``. Also verifies that
revoking a grant clears the cache so the gate denies immediately.

The schema is provisioned by the session-scoped ``init_test_database`` fixture.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from myrm_agent_harness.agent.middlewares.guardrails import (
    GuardrailMiddleware,
    SkillBoundaryProvider,
)
from myrm_agent_harness.agent.skill_agent.context import (
    reset_loaded_skills,
    set_loaded_skills,
)
from myrm_agent_harness.agent.skills import SkillMetadata
from myrm_agent_harness.backends.skills import SkillPermission
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import SkillPermissionGrant
from app.services.skills.permission_service import (
    clear_permission_cache,
    create_async_permission_checker,
)

_LOADED_SKILL = "demo_skill"


@pytest.fixture(autouse=True)
async def _clean_skill_state() -> None:
    """Isolate per test: reset loaded skills, cache, and DB grant rows."""

    async def _purge() -> None:
        async with get_session() as db:
            await db.execute(
                delete(SkillPermissionGrant).where(
                    SkillPermissionGrant.skill_id == _LOADED_SKILL
                )
            )
            await db.commit()

    reset_loaded_skills()
    clear_permission_cache()
    await _purge()
    yield
    reset_loaded_skills()
    clear_permission_cache()
    await _purge()


async def _grant(*permissions: SkillPermission) -> None:
    async with get_session() as db:
        for perm in permissions:
            db.add(
                SkillPermissionGrant(
                    skill_id=_LOADED_SKILL, permission=perm.value
                )
            )
        await db.commit()


async def _revoke() -> None:
    async with get_session() as db:
        await db.execute(
            delete(SkillPermissionGrant).where(
                SkillPermissionGrant.skill_id == _LOADED_SKILL
            )
        )
        await db.commit()


def _request(tool_name: str, args: dict[str, object]) -> ToolCallRequest:
    return ToolCallRequest(
        tool=MagicMock(),
        state={},
        runtime=MagicMock(),
        tool_call={"name": tool_name, "args": args, "id": "call_1"},
    )


async def _handler(req: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id="call_1")


async def _gate() -> GuardrailMiddleware:
    set_loaded_skills([SkillMetadata(name=_LOADED_SKILL, description="d", version="1.0.0")])
    checker = await create_async_permission_checker()
    return GuardrailMiddleware(
        providers=[SkillBoundaryProvider(permission_checker=checker)]
    )


@pytest.mark.asyncio
async def test_real_db_grant_allows_tool() -> None:
    """A CODE_INTERPRETER grant row must let bash_code_execute_tool through."""
    await _grant(SkillPermission.CODE_INTERPRETER)
    mw = await _gate()

    result = await mw.awrap_tool_call(
        _request("bash_code_execute_tool", {"command": "echo hi"}), _handler
    )
    assert result.content == "ok"
    assert result.status != "error"


@pytest.mark.asyncio
async def test_real_db_ungranted_denies_tool() -> None:
    """Without any grant row, a sensitive edit tool must be blocked."""
    mw = await _gate()

    result = await mw.awrap_tool_call(
        _request("file_edit_tool", {"path": "/tmp/x.py", "edits": [{"old": "a", "new": "b"}]}),
        _handler,
    )
    assert result.status == "error"
    assert "skill_boundary" in str(result.content)


@pytest.mark.asyncio
async def test_real_db_partial_grant_still_denies() -> None:
    """FILE_READ alone must not authorize FILE_WRITE-level edits."""
    await _grant(SkillPermission.FILE_READ)
    mw = await _gate()

    result = await mw.awrap_tool_call(
        _request("file_edit_tool", {"path": "/tmp/x.py", "edits": [{"old": "a", "new": "b"}]}),
        _handler,
    )
    assert result.status == "error"
    assert "skill_boundary" in str(result.content)


@pytest.mark.asyncio
async def test_real_db_revoke_clears_cache_and_denies_immediately() -> None:
    """Revoking the grant + clearing the cache must take effect immediately."""
    await _grant(SkillPermission.CODE_INTERPRETER)
    mw = await _gate()

    allowed = await mw.awrap_tool_call(
        _request("bash_code_execute_tool", {"command": "echo hi"}), _handler
    )
    assert allowed.content == "ok"

    await _revoke()
    clear_permission_cache()

    denied = await mw.awrap_tool_call(
        _request("bash_code_execute_tool", {"command": "echo hi"}), _handler
    )
    assert denied.status == "error"
    assert "skill_boundary" in str(denied.content)


@pytest.mark.asyncio
async def test_real_db_dirty_value_is_skipped() -> None:
    """An unknown permission value must be ignored, not crash the gate."""
    async with get_session() as db:
        db.add(SkillPermissionGrant(skill_id=_LOADED_SKILL, permission="not-a-permission"))
        db.add(SkillPermissionGrant(skill_id=_LOADED_SKILL, permission=SkillPermission.FILE_READ.value))
        await db.commit()

    mw = await _gate()
    result = await mw.awrap_tool_call(
        _request("grep_tool", {"pattern": "x", "path": "/tmp"}), _handler
    )
    assert result.content == "ok"
