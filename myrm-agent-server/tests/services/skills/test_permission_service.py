"""Unit tests for Skill Permission Service.

Covers the async permission checker's audit logging (argument order must match
the framework log_permission_usage signature: user_id first), the per-session
permission cache path, and the sync checker's async-context fail-fast guard.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.backends.skills import SkillPermission

from app.services.skills import permission_service
from app.services.skills.permission_service import (
    create_async_permission_checker,
    load_granted_permissions,
    load_granted_permissions_cached,
)


@pytest.fixture(autouse=True)
def _reset_permission_cache() -> None:
    permission_service._permission_cache.clear()
    yield
    permission_service._permission_cache.clear()


@pytest.mark.asyncio
async def test_async_checker_logs_with_correct_argument_order() -> None:
    """log_permission_usage must receive (user_id, skill_id, permission, operation, allowed, deny_reason)."""
    from myrm_agent_harness.backends.skills import session_id_var

    token = session_id_var.set("sess-abc")
    try:
        with (
            patch(
                "app.services.skills.permission_service.load_granted_permissions_cached",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.services.skills.permission_service.check_permission_for_tool_call",
                return_value=(True, ""),
            ),
            patch(
                "app.services.skills.permission_service.log_permission_usage"
            ) as mock_log,
        ):
            checker = await create_async_permission_checker()
            allowed, reason = await checker("demo-skill", "file_write", "/tmp/x.txt")
    finally:
        session_id_var.reset(token)

    assert (allowed, reason) == (True, "")
    mock_log.assert_called_once_with(
        "sess-abc",
        "demo-skill",
        "file_write",
        "/tmp/x.txt",
        True,
        "",
    )


@pytest.mark.asyncio
async def test_async_checker_falls_back_to_default_session() -> None:
    """Without an explicit session id, the harness default 'default_session' is used."""
    with (
        patch(
            "app.services.skills.permission_service.load_granted_permissions_cached",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "app.services.skills.permission_service.check_permission_for_tool_call",
            return_value=(False, "denied by policy"),
        ),
        patch(
            "app.services.skills.permission_service.log_permission_usage"
        ) as mock_log,
    ):
        checker = await create_async_permission_checker()
        allowed, reason = await checker("demo-skill", "shell_exec", "rm -rf /")

    assert (allowed, reason) == (False, "denied by policy")
    mock_log.assert_called_once_with(
        "default_session",
        "demo-skill",
        "shell_exec",
        "rm -rf /",
        False,
        "denied by policy",
    )


@pytest.mark.asyncio
async def test_async_checker_returns_validation_result() -> None:
    """The checker must surface the framework validation result unchanged."""
    granted = MagicMock()
    with (
        patch(
            "app.services.skills.permission_service.load_granted_permissions_cached",
            new=AsyncMock(return_value={granted}),
        ),
        patch(
            "app.services.skills.permission_service.check_permission_for_tool_call",
            return_value=(True, ""),
        ),
        patch("app.services.skills.permission_service.log_permission_usage"),
    ):
        checker = await create_async_permission_checker()
        allowed, _ = await checker("demo-skill", "read", "/tmp/readme")

    assert allowed is True


@pytest.mark.asyncio
async def test_async_checker_reads_through_per_session_cache() -> None:
    """The async checker must load grants via the cached loader, not the DB each call."""
    with (
        patch(
            "app.services.skills.permission_service.load_granted_permissions_cached"
        ) as mock_load,
        patch(
            "app.services.skills.permission_service.check_permission_for_tool_call",
            return_value=(True, ""),
        ),
        patch("app.services.skills.permission_service.log_permission_usage"),
    ):
        mock_load.return_value = set()
        checker = await create_async_permission_checker()
        allowed, _ = await checker("demo-skill", "file_write", "/tmp/x.txt")

    assert allowed is True
    mock_load.assert_awaited_once_with("demo-skill")


@pytest.mark.asyncio
async def test_sync_checker_fails_fast_inside_running_loop() -> None:
    """The sync checker must refuse to run asyncio.run inside a running loop."""
    from app.services.skills.permission_service import create_permission_checker

    checker = create_permission_checker()
    with pytest.raises(RuntimeError, match="create_async_permission_checker"):
        checker("demo-skill", "file_write", "/tmp/x.txt")


def test_sync_checker_works_outside_event_loop() -> None:
    """Outside an event loop the sync checker must still execute and log."""
    from app.services.skills.permission_service import create_permission_checker

    with (
        patch(
            "app.services.skills.permission_service.load_granted_permissions_cached",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "app.services.skills.permission_service.check_permission_for_tool_call",
            return_value=(False, "denied by policy"),
        ),
        patch(
            "app.services.skills.permission_service.log_permission_usage"
        ) as mock_log,
    ):
        checker = create_permission_checker()
        allowed, reason = checker("demo-skill", "shell_exec", "rm -rf /")

    assert (allowed, reason) == (False, "denied by policy")
    mock_log.assert_called_once()
    args = mock_log.call_args[0]
    assert args[1] == "demo-skill"
    assert args[2] == "shell_exec"


@patch("app.services.skills.permission_service.get_session")
async def test_load_granted_permissions_reads_db_and_filters_invalid(
    mock_session: AsyncMock,
) -> None:
    """DB values map to enums; unknown values are skipped with a warning."""
    valid_grant = MagicMock(permission="file_write")
    invalid_grant = MagicMock(permission="not-a-permission")

    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [
        valid_grant,
        invalid_grant,
    ]
    db_mock.execute.return_value = result_mock
    mock_session.return_value.__aenter__.return_value = db_mock

    permissions = await load_granted_permissions("skill-1")
    assert permissions == {SkillPermission.FILE_WRITE}


@patch("app.services.skills.permission_service.load_granted_permissions")
async def test_cached_loader_hits_cache_without_db(mock_load: AsyncMock) -> None:
    """A warm cache must not touch the database loader."""
    permission_service._permission_cache["skill-1"] = {SkillPermission.FILE_READ}

    permissions = await load_granted_permissions_cached("skill-1")
    assert permissions == {SkillPermission.FILE_READ}
    mock_load.assert_not_awaited()


@patch("app.services.skills.permission_service.load_granted_permissions")
async def test_cached_loader_populates_on_miss(mock_load: AsyncMock) -> None:
    """A cache miss loads from DB and stores the result."""
    mock_load.return_value = {SkillPermission.SHELL_EXEC}

    first = await load_granted_permissions_cached("skill-1")
    second = await load_granted_permissions_cached("skill-1")

    assert first == second == {SkillPermission.SHELL_EXEC}
    mock_load.assert_awaited_once_with("skill-1")
    assert permission_service._permission_cache["skill-1"] == {
        SkillPermission.SHELL_EXEC
    }


def test_clear_permission_cache_all() -> None:
    permission_service._permission_cache.update(
        {"a": set(), "b": {SkillPermission.FILE_READ}}
    )
    permission_service.clear_permission_cache()
    assert permission_service._permission_cache == {}


def test_clear_permission_cache_specific_skill() -> None:
    permission_service._permission_cache.update(
        {"a": set(), "b": {SkillPermission.FILE_READ}}
    )
    permission_service.clear_permission_cache("a")
    assert list(permission_service._permission_cache) == ["b"]


def test_clear_permission_cache_missing_skill_is_noop() -> None:
    permission_service.clear_permission_cache("unknown")
    assert permission_service._permission_cache == {}
