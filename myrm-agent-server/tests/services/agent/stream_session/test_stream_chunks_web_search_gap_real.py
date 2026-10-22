"""generate_cancellable_stream really emits the web_search config-gap preflight.

The sibling test module mirrors the branch in a local helper, so it cannot catch a regression in the
generator itself (ordering, the collector feed, or envelope construction). This drives the real
generator and asserts the SSE chunk the browser would receive.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session import stream_chunks
from app.services.agent.stream_session.entitlement_gap_preflight import (
    reset_capability_gap_emission_tracker,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

_NO_CHUNKS: tuple[str, ...] = ()


def _session(*, profile_enabled: bool, runtime_enabled: bool) -> AgentStreamSession:
    return AgentStreamSession(
        request=AgentRequest(
            message_id="msg-gap",
            chat_id="chat-gap",
            query="search today's news",
        ),
        http_request=cast(Request, None),
        params=GeneralAgentParams(
            message_id="msg-gap",
            chat_id="chat-gap",
            query="search today's news",
            model_cfg=ModelConfig(model="claude-3-7-sonnet", api_key="sk-test"),
            web_search_profile_enabled=profile_enabled,
            enable_web_search=runtime_enabled,
            search_is_user_configured=False,
        ),
        cancel_token=CancellationToken(request_id="msg-gap"),
        steering_token=None,
        routing_tier=None,
        archive_restore_results=[],
        research_model_cfg=None,
        registry=cast(GlobalStreamRegistry, None),
        collector=StreamContentCollector(chat_id="chat-gap"),
        is_long_running_task=False,
        goal_provider=None,
        extra_context={},
    )


async def _collect_chunks(session: AgentStreamSession) -> list[str]:
    @asynccontextmanager
    async def noop_watch(_session: AgentStreamSession) -> AsyncIterator[None]:
        yield

    async def no_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for chunk in _NO_CHUNKS:
            yield chunk

    async def no_exception_chunks(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for chunk in _NO_CHUNKS:
            yield chunk

    async def no_finalize(*_args: object, **_kwargs: object) -> None:
        return None

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.agent.stream_session.migration_readiness_preflight.resolve_and_build_migration_readiness_gap_sse_event",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        patch.object(stream_chunks, "watch_client_disconnect", noop_watch),
        patch.object(stream_chunks, "iter_agent_stream_chunks", no_stream),
        patch.object(stream_chunks, "yield_stream_exception_chunks", no_exception_chunks),
        patch.object(stream_chunks, "finalize_agent_stream_session", no_finalize),
    ):
        return [chunk async for chunk in stream_chunks.generate_cancellable_stream(session) if chunk.strip()]


@pytest.mark.asyncio
async def test_generator_emits_web_search_capability_gap() -> None:
    """A profile that wants search while runtime search is unavailable yields the gap chunk."""
    reset_capability_gap_emission_tracker()

    chunks = await _collect_chunks(_session(profile_enabled=True, runtime_enabled=False))

    gap_chunks = [chunk for chunk in chunks if "capability_gap" in chunk]
    assert gap_chunks, f"expected a capability_gap chunk, got {chunks!r}"
    payload = json.loads(gap_chunks[0].removeprefix("data: ").strip())
    assert payload["type"] == "capability_gap"
    assert payload["data"]["tool_id"] == "web_search"


@pytest.mark.asyncio
async def test_generator_stays_silent_when_runtime_search_works() -> None:
    """No gap when the runtime can search, so the toast never fires on a healthy setup."""
    reset_capability_gap_emission_tracker()

    chunks = await _collect_chunks(_session(profile_enabled=True, runtime_enabled=True))

    assert not [chunk for chunk in chunks if "capability_gap" in chunk], chunks
