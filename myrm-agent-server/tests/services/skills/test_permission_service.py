"""Unit tests for Skill Permission Service.

Covers the async permission checker's audit logging: argument order must match
the framework log_permission_usage signature (user_id first) and the current
session id must be forwarded when available.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.skills.permission_service import create_async_permission_checker


@pytest.mark.asyncio
async def test_async_checker_logs_with_correct_argument_order() -> None:
    """log_permission_usage must receive (user_id, skill_id, permission, operation, allowed, deny_reason)."""
    from myrm_agent_harness.backends.skills import session_id_var

    token = session_id_var.set("sess-abc")
    try:
        with (
            patch(
                "app.services.skills.permission_service.load_granted_permissions",
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
            "app.services.skills.permission_service.load_granted_permissions",
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
            "app.services.skills.permission_service.load_granted_permissions",
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
