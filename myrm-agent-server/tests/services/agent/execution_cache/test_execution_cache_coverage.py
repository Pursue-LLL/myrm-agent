"""Additional coverage for execution_cache edge paths."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache.fingerprint import (
    _stable_json,
    build_execution_scope_key,
    compute_execution_fingerprint,
)
from app.services.agent.execution_cache.registry import (
    ChatAgentExecutionCache,
    close_execution_cache_for_chat,
    close_execution_cache_for_chat_all_agents,
    get_execution_cache,
)
from app.services.agent.execution_cache.session_lifecycle import (
    finalize_agent_session,
    resolve_execution_mode,
)
from app.services.agent.execution_cache.types import BuiltExecutionUnit, ExecutionMode


def test_stable_json_nested_and_model_dump() -> None:
    class Dumpable:
        def model_dump(self, *, mode: str = "json") -> dict[str, object]:
            return {"z": 1, "nested": {"a": 2}}

    assert _stable_json({"b": 1, "a": [Dumpable()]}) == {"a": [{"nested": {"a": 2}, "z": 1}], "b": 1}

    class Plain:
        def __str__(self) -> str:
            return "plain-value"

    assert _stable_json(Plain()) == "plain-value"


def test_build_execution_scope_key_edge_cases() -> None:
    assert build_execution_scope_key(None, "a") is None
    assert build_execution_scope_key("  ", "a") is None
    assert build_execution_scope_key(" chat ", None) == "chat:default"


def test_compute_execution_fingerprint_includes_mcp() -> None:
    mcp_cfg = MagicMock()
    mcp_cfg.model_dump.return_value = {"name": "github", "url": "http://mcp"}
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="m", api_key="k", base_url="http://x"),
        mcp_config=[mcp_cfg],
        engine_params={"nested": {"x": 1}},
        skill_configs={"s1": {"k": "v"}},
    )
    first = compute_execution_fingerprint(wrapper)
    mcp_cfg.model_dump.return_value = {"name": "github", "url": "http://other"}
    second = compute_execution_fingerprint(wrapper)
    assert first != second


@pytest.mark.asyncio
async def test_built_execution_unit_teardown_closes_all_resources() -> None:
    browser = MagicMock()
    browser.close = AsyncMock(side_effect=RuntimeError("browser boom"))
    desktop = MagicMock()
    desktop.close = MagicMock(return_value=None)
    skill_agent = MagicMock()
    skill_agent.close = AsyncMock()

    unit = BuiltExecutionUnit(
        skill_agent=skill_agent,
        browser_session=browser,
        desktop_session=desktop,
        checkpoint_helper=object(),
        current_thread_id="t1",
    )
    await unit.teardown()

    browser.close.assert_awaited_once()
    desktop.close.assert_called_once()
    skill_agent.close.assert_awaited_once()
    assert unit.browser_session is None
    assert unit.desktop_session is None
    assert unit.checkpoint_helper is None
    assert unit.current_thread_id is None


@pytest.mark.asyncio
async def test_built_execution_unit_teardown_desktop_close_raises() -> None:
    desktop = MagicMock()
    desktop.close = AsyncMock(side_effect=RuntimeError("desktop boom"))
    skill_agent = MagicMock()
    skill_agent.close = AsyncMock()

    unit = BuiltExecutionUnit(skill_agent=skill_agent, desktop_session=desktop)
    await unit.teardown()

    desktop.close.assert_awaited_once()
    skill_agent.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_registry_idle_eviction() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=0.01)

    async def build_unit() -> BuiltExecutionUnit:
        skill = MagicMock()
        skill.close = AsyncMock()
        return BuiltExecutionUnit(skill_agent=skill)

    first = await registry.acquire("chat-1:default", "fp-a", build_unit)
    await registry.release("chat-1:default")
    await asyncio.sleep(0.02)
    second = await registry.acquire("chat-2:default", "fp-a", build_unit)
    assert first.skill_agent is not second.skill_agent
    first.skill_agent.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_registry_defer_replace_during_active_turn() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=3600.0)
    skill = MagicMock()
    skill.close = AsyncMock()
    unit = BuiltExecutionUnit(skill_agent=skill)
    build_count = 0

    async def build_one() -> BuiltExecutionUnit:
        nonlocal build_count
        build_count += 1
        return unit

    first = await registry.acquire("chat-3:default", "fp-a", build_one)
    release = asyncio.Event()

    async def holding_turn() -> None:
        async with registry.guard_turn("chat-3:default"):
            await release.wait()

    turn_task = asyncio.create_task(holding_turn())
    await asyncio.sleep(0.02)

    second = await registry.acquire("chat-3:default", "fp-b", build_one)
    assert second is first
    skill.close.assert_not_called()
    assert build_count == 1

    release.set()
    await turn_task

    third = await registry.acquire("chat-3:default", "fp-b", build_one)
    assert third is unit
    skill.close.assert_awaited_once()
    assert build_count == 2


@pytest.mark.asyncio
async def test_registry_guard_turn_noop_for_empty_scope() -> None:
    registry = ChatAgentExecutionCache()
    async with registry.guard_turn(None):
        pass
    async with registry.guard_turn(""):
        pass


@pytest.mark.asyncio
async def test_close_execution_cache_helpers() -> None:
    cache = get_execution_cache()

    async def build_unit() -> BuiltExecutionUnit:
        skill = MagicMock()
        skill.close = AsyncMock()
        return BuiltExecutionUnit(skill_agent=skill)

    await cache.acquire("chat-x:default", "fp", build_unit)
    await close_execution_cache_for_chat("chat-x", agent_id="default")
    await close_execution_cache_for_chat(None)
    await close_execution_cache_for_chat_all_agents("")


def test_resolve_execution_mode() -> None:
    assert resolve_execution_mode(None) == ExecutionMode.POOLED
    assert resolve_execution_mode({"execution_mode": "ephemeral"}) == ExecutionMode.EPHEMERAL
    assert resolve_execution_mode({"execution_mode": ExecutionMode.EPHEMERAL}) == ExecutionMode.EPHEMERAL


@pytest.mark.asyncio
async def test_finalize_agent_session_ephemeral_closes_agent() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="m", api_key="k", base_url="http://x"),
        mcp_config=None,
    )
    skill = MagicMock()
    skill.close = AsyncMock()
    wrapper.agent = skill
    wrapper.close = AsyncMock()

    await finalize_agent_session(
        wrapper,
        chat_id="c1",
        agent_id="a1",
        extra_context={"execution_mode": ExecutionMode.EPHEMERAL},
    )
    wrapper.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_pooled_swallows_release_errors() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="m", api_key="k", base_url="http://x"),
        mcp_config=None,
        chat_id="c2",
        agent_id="a2",
    )
    skill = MagicMock()
    wrapper.agent = skill
    wrapper.release_pooled_session = AsyncMock(side_effect=RuntimeError("boom"))

    with patch(
        "app.services.agent.execution_cache.session_lifecycle.get_execution_cache",
    ) as cache_mock:
        cache_mock.return_value.refresh_unit = AsyncMock(side_effect=RuntimeError("refresh"))
        cache_mock.return_value.release = AsyncMock(side_effect=RuntimeError("release"))
        await finalize_agent_session(
            wrapper,
            chat_id="c2",
            agent_id="a2",
            extra_context={"execution_mode": ExecutionMode.POOLED},
        )

    assert wrapper.agent is None
