"""Shared fixtures for the turn-pipeline step tests: a message builder, a router whose preparation and execution are
recorders, and the helpers that read what the pipeline handed to them."""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_state_key
from app.channels.types import InboundMessage

from ..risk_gate_testkit import make_router

TURN = "app.channels.routing.pipeline.turn"
STATE_KEY = routing_state_key("telegram", "chat-1", None)


def turn_msg(
    content: str = "hello",
    *,
    message_id: str = "m1",
    metadata: dict[str, object] | None = None,
    resume_value: dict[str, object] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="chat-1",
        content=content,
        message_id=message_id,
        metadata=metadata or {},
        resume_value=resume_value,
    )


def turn_router(*, prepared_chat_id: str = "chat-1", exec_content: str | None = None) -> AgentRouter:
    """A router whose run is recorded: the preparation hands back a context, the execution does nothing."""
    router = make_router()
    router._gate = MagicMock()
    router._fx = MagicMock(
        reactions=MagicMock(
            accepted=MagicMock(side_effect=lambda _channel, preferred, _fallbacks: preferred),
            react=AsyncMock(),
        ),
        cleanup_placeholder=AsyncMock(),
        send_error_reply=AsyncMock(),
    )

    async def prepare(inbound: InboundMessage) -> SimpleNamespace:
        exec_msg = inbound if exec_content is None else dataclasses.replace(inbound, content=exec_content)
        return SimpleNamespace(chat_id=prepared_chat_id, exec_msg=exec_msg)

    router._prepare_execution_context = AsyncMock(side_effect=prepare)  # type: ignore[method-assign]
    router._execute_prepared_context = AsyncMock()  # type: ignore[method-assign]
    router._retire_open_approval = AsyncMock()  # type: ignore[method-assign]
    return router


def shown_reactions(router: AgentRouter) -> list[tuple[str, str, str, str]]:
    """Every reaction call the turn made, as (channel, chat, message, emoji); an empty emoji takes the reaction off."""
    react = cast("AsyncMock", router._fx.reactions.react)
    return [tuple(call.args) for call in react.await_args_list]


def prepared_message(router: AgentRouter) -> InboundMessage:
    prepare = cast("AsyncMock", router._prepare_execution_context)
    assert prepare.await_args is not None
    prepared: InboundMessage = prepare.await_args.args[0]
    return prepared


def execution_kwargs(router: AgentRouter) -> dict[str, object]:
    """The keyword arguments the turn started its run with."""
    run = cast("AsyncMock", router._execute_prepared_context)
    assert run.await_args is not None
    return dict(run.await_args.kwargs)


def attach_journal(router: AgentRouter) -> MagicMock:
    journal = MagicMock()
    router.set_inbound_journal(journal)
    return journal


def tag_enricher(name: str) -> Callable[..., InboundMessage]:
    """An enricher that leaves a mark on the content, to show the order the steps ran in."""

    def enrich(inbound: InboundMessage, *_: object, **__: object) -> InboundMessage:
        return dataclasses.replace(inbound, content=f"{inbound.content}+{name}")

    return enrich


def tag_enricher_async(name: str) -> Callable[..., Awaitable[InboundMessage]]:
    sync = tag_enricher(name)

    async def enrich(inbound: InboundMessage, *args: object, **kwargs: object) -> InboundMessage:
        return sync(inbound, *args, **kwargs)

    return enrich
