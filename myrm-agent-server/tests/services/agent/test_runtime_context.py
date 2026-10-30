"""Unit tests for build_agent_runtime_context."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.execution_cache import ExecutionMode
from app.services.agent.runtime_context import (
    SINGLE_TENANT_USER_ID,
    build_agent_runtime_context,
    resolve_stream_execution_mode,
)


@pytest.mark.asyncio
async def test_build_agent_runtime_context_merges_base_and_roots() -> None:
    with patch(
        "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        return_value=["/skills/off"],
    ):
        ctx = await build_agent_runtime_context(
            execution_mode=ExecutionMode.POOLED,
            base={"goal_provider": "mock"},
        )

    assert ctx["execution_mode"] is ExecutionMode.POOLED
    assert ctx["goal_provider"] == "mock"
    assert ctx["disabled_skill_roots"] == ["/skills/off"]


@pytest.mark.asyncio
async def test_build_agent_runtime_context_carries_the_single_tenant_user_id() -> None:
    """Harness skill tools (skill_manage, skill_market install/uninstall) read context["user_id"]."""
    with patch(
        "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_agent_runtime_context(execution_mode=ExecutionMode.POOLED)

    assert ctx["user_id"] == SINGLE_TENANT_USER_ID


@pytest.mark.asyncio
async def test_build_agent_runtime_context_keeps_a_caller_supplied_user_id() -> None:
    with patch(
        "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_agent_runtime_context(
            execution_mode=ExecutionMode.POOLED,
            base={"user_id": "paired_member_slack_U1"},
        )

    assert ctx["user_id"] == "paired_member_slack_U1"


@pytest.mark.asyncio
async def test_build_agent_runtime_context_defaults_roots_on_failure() -> None:
    with patch(
        "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        ctx = await build_agent_runtime_context(execution_mode=ExecutionMode.EPHEMERAL)

    assert ctx["execution_mode"] is ExecutionMode.EPHEMERAL
    assert ctx["disabled_skill_roots"] == []


def test_resolve_stream_execution_mode_defaults_pooled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert resolve_stream_execution_mode() is ExecutionMode.POOLED
