"""Live integration: chat-scoped RuntimePool registry (no mocks on pool/registry path)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin
from app.services.external_agents.runtime_pool_registry import (
    ChatScopedRuntimePoolFacade,
    get_chat_runtime_pool_registry,
)

_ECHO_AGENT_CFG: list[dict[str, object]] = [
    {
        "name": "echo-cli",
        "type": "cli",
        "command": "echo",
        "args": [],
    }
]


@pytest.fixture(autouse=True)
async def _reset_registry() -> None:
    await get_chat_runtime_pool_registry().close_all()
    yield
    await get_chat_runtime_pool_registry().close_all()


def _new_mixin(*, chat_scope_id: str) -> ExternalAgentsMixin:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = _ECHO_AGENT_CFG
    mixin._runtime_pool_scope_id = chat_scope_id
    mixin._runtime_pool = None
    mixin._runtime_pool_from_registry = False
    mixin._runtime_pool_ephemeral = False
    mixin.agent_id = "general"
    mixin.force_delegate_agent = None
    return mixin


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_setup_reuses_registry_pool_and_wraps_facade() -> None:
    """Two setups on the same chat must share the raw RuntimePool via registry."""
    chat_id = "live-int-chat-reuse"

    mixin_a = _new_mixin(chat_scope_id=chat_id)
    await mixin_a._do_setup_external_agents([], [], mount_delegate_tool=False)

    assert isinstance(mixin_a._runtime_pool, ChatScopedRuntimePoolFacade)
    assert mixin_a._runtime_pool_from_registry is True
    raw_a = mixin_a._runtime_pool._pool

    mixin_b = _new_mixin(chat_scope_id=chat_id)
    await mixin_b._do_setup_external_agents([], [], mount_delegate_tool=False)

    assert isinstance(mixin_b._runtime_pool, ChatScopedRuntimePoolFacade)
    raw_b = mixin_b._runtime_pool._pool
    assert raw_a is raw_b


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_guard_turn_serializes_concurrent_run_turn() -> None:
    """Concurrent run_turn on same chat must not overlap (real Facade + registry)."""
    mixin = _new_mixin(chat_scope_id="live-int-chat-serialize")
    await mixin._do_setup_external_agents([], [], mount_delegate_tool=False)
    assert mixin._runtime_pool is not None

    order: list[str] = []
    gate = asyncio.Event()
    release = asyncio.Event()

    async def slow_run(
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
    ):
        order.append(f"{name}_start")
        gate.set()
        await release.wait()
        yield MagicMock()

    pool = mixin._runtime_pool
    assert isinstance(pool, ChatScopedRuntimePoolFacade)
    original_run_turn = pool._pool.run_turn
    pool._pool.run_turn = slow_run  # type: ignore[method-assign]

    async def consume(label: str) -> None:
        async for _ in pool.run_turn("echo-cli", label, f"s-{label}"):
            pass

    try:
        task1 = asyncio.create_task(consume("first"))
        await asyncio.wait_for(gate.wait(), timeout=2.0)
        task2 = asyncio.create_task(consume("second"))
        await asyncio.sleep(0.05)
        assert order == ["echo-cli_start"]
        release.set()
        await asyncio.gather(task1, task2)
        assert order == ["echo-cli_start", "echo-cli_start"]
    finally:
        pool._pool.run_turn = original_run_turn


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_release_preserves_pool_for_next_message() -> None:
    """release() after a message must keep CLI pool alive for the next acquire."""
    registry = get_chat_runtime_pool_registry()
    chat_id = "live-int-chat-release"

    mixin_a = _new_mixin(chat_scope_id=chat_id)
    await mixin_a._do_setup_external_agents([], [], mount_delegate_tool=False)
    assert isinstance(mixin_a._runtime_pool, ChatScopedRuntimePoolFacade)
    raw_pool = mixin_a._runtime_pool._pool

    await registry.release(chat_id)

    mixin_b = _new_mixin(chat_scope_id=chat_id)
    await mixin_b._do_setup_external_agents([], [], mount_delegate_tool=False)
    assert mixin_b._runtime_pool._pool is raw_pool


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ephemeral_scope_skips_registry_facade() -> None:
    """Without chat scope the pool is ephemeral (no Facade, no registry acquire)."""
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = _ECHO_AGENT_CFG
    mixin._runtime_pool_scope_id = None
    mixin._runtime_pool = None
    mixin._runtime_pool_from_registry = False
    mixin._runtime_pool_ephemeral = False
    mixin.agent_id = "general"
    mixin.force_delegate_agent = None

    await mixin._do_setup_external_agents([], [], mount_delegate_tool=False)

    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool

    assert isinstance(mixin._runtime_pool, RuntimePool)
    assert mixin._runtime_pool_from_registry is False
    assert mixin._runtime_pool_ephemeral is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_facade_cancel_during_active_run_turn() -> None:
    """Cancel must complete while run_turn holds the chat lock (production stop path)."""
    mixin = _new_mixin(chat_scope_id="live-int-chat-cancel")
    await mixin._do_setup_external_agents([], [], mount_delegate_tool=False)
    pool = mixin._runtime_pool
    assert isinstance(pool, ChatScopedRuntimePoolFacade)

    entered = asyncio.Event()
    unblock = asyncio.Event()
    cancel_called = asyncio.Event()

    async def slow_run(
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
    ):
        entered.set()
        await unblock.wait()
        yield MagicMock()

    original_run_turn = pool._pool.run_turn
    original_cancel = pool._pool.cancel

    async def track_cancel(name: str, session_id: str) -> None:
        cancel_called.set()
        await original_cancel(name, session_id)

    pool._pool.run_turn = slow_run  # type: ignore[method-assign]
    pool._pool.cancel = track_cancel  # type: ignore[method-assign]

    async def consume() -> None:
        async for _ in pool.run_turn("echo-cli", "hi", "sess-1"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.wait_for(pool.cancel("echo-cli", "sess-1"), timeout=2.0)
    await asyncio.wait_for(cancel_called.wait(), timeout=2.0)
    unblock.set()
    await task

    pool._pool.run_turn = original_run_turn
    pool._pool.cancel = original_cancel


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_fingerprint_replace_deferred_while_turn_locked() -> None:
    """Config fingerprint change during active run_turn must defer pool replace."""
    chat_id = "live-int-chat-fp-defer"
    registry = get_chat_runtime_pool_registry()

    mixin_a = _new_mixin(chat_scope_id=chat_id)
    await mixin_a._do_setup_external_agents([], [], mount_delegate_tool=False)
    pool = mixin_a._runtime_pool
    assert isinstance(pool, ChatScopedRuntimePoolFacade)
    raw_first = pool._pool

    entered = asyncio.Event()
    unblock = asyncio.Event()

    async def slow_run(
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
    ):
        entered.set()
        await unblock.wait()
        yield MagicMock()

    original_run_turn = pool._pool.run_turn
    pool._pool.run_turn = slow_run  # type: ignore[method-assign]

    async def consume() -> None:
        async for _ in pool.run_turn("echo-cli", "hold", "sess-hold"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(entered.wait(), timeout=2.0)

    alt_cfg: list[dict[str, object]] = [
        {
            "name": "echo-cli",
            "type": "cli",
            "command": "echo",
            "args": ["alt"],
        }
    ]
    mixin_b = _new_mixin(chat_scope_id=chat_id)
    mixin_b.external_agents_config = alt_cfg
    await mixin_b._do_setup_external_agents([], [], mount_delegate_tool=False)
    assert mixin_b._runtime_pool._pool is raw_first

    unblock.set()
    await task
    pool._pool.run_turn = original_run_turn

    mixin_c = _new_mixin(chat_scope_id=chat_id)
    mixin_c.external_agents_config = alt_cfg
    await mixin_c._do_setup_external_agents([], [], mount_delegate_tool=False)
    assert mixin_c._runtime_pool._pool is not raw_first

