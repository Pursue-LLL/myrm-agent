"""Shared builders for inbound risk gate tests: a router over a stub bus."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.channels.routing.router import AgentRouter


def make_bus() -> MagicMock:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


def make_router(bus: MagicMock | None = None) -> AgentRouter:
    return AgentRouter(
        bus=bus or make_bus(),
        pairing_store=MagicMock(),
        agent_executor=MagicMock(),
    )
