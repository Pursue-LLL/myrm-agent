"""Unit tests for build_agent_runtime_context."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.execution_cache import ExecutionMode
from app.services.agent.params.models import AgentRequest
from app.services.agent.runtime_context import build_agent_runtime_context, prefer_direct_agent_stream


@pytest.mark.asyncio
async def test_build_agent_runtime_context_merges_base_and_roots() -> None:
    with patch(
        "app.core.skills.disabled_skill_roots.collect_disabled_skill_roots",
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
async def test_build_agent_runtime_context_defaults_roots_on_failure() -> None:
    with patch(
        "app.core.skills.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        ctx = await build_agent_runtime_context(execution_mode=ExecutionMode.EPHEMERAL)

    assert ctx["execution_mode"] is ExecutionMode.EPHEMERAL
    assert ctx["disabled_skill_roots"] == []


def test_prefer_direct_agent_stream_for_shpoib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_E2E_SHPOIB", "1")
    request = AgentRequest(message_id="m1", chat_id="c1", query="hi", multiplexed=True)
    resolved = prefer_direct_agent_stream(request)
    assert resolved.multiplexed is False


def test_prefer_direct_agent_stream_skips_without_shpoib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_E2E_SHPOIB", raising=False)
    request = AgentRequest(message_id="m1", chat_id="c1", query="hi", multiplexed=True)
    resolved = prefer_direct_agent_stream(request)
    assert resolved.multiplexed is True
