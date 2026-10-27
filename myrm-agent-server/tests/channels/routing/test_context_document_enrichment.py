"""A turn's reference document is asked of its channel right before the agent runs, and never earlier."""

from __future__ import annotations

import logging
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.routing import context_document as enrichment
from app.channels.routing.context_document import enrich_context_document
from app.channels.routing.router_execution import RouterExecutionMixin
from app.channels.routing.router_models import _ActiveTask, _AgentTurnScratch, _RouterExecutionContext
from app.channels.types import (
    METADATA_CONTEXT_DOCUMENT_KEY,
    ContextDocument,
    InboundMessage,
    OutboundMessage,
)


class _PlainChannel(BaseChannel):
    name = "plain"

    async def send(self, msg: OutboundMessage) -> str | None:
        return None


class _DocumentChannel(_PlainChannel):
    def __init__(self, document: ContextDocument | None = None, *, fault: Exception | None = None) -> None:
        super().__init__()
        self._document = document
        self._fault = fault
        self.asked: list[InboundMessage] = []

    async def read_context_document(self, msg: InboundMessage) -> ContextDocument | None:
        self.asked.append(msg)
        if self._fault is not None:
            raise self._fault
        return self._document


def _inbound() -> InboundMessage:
    return InboundMessage(channel="plain", sender_id="u1", content="summarize", chat_id="c1", metadata={"locale": "en"})


def _lookup(channel: BaseChannel | None) -> Callable[[str], BaseChannel | None]:
    return lambda name: channel


async def test_the_channels_document_rides_in_a_new_metadata_dict() -> None:
    document = ContextDocument.ready("# Plan")
    msg = _inbound()

    enriched = await enrich_context_document(msg, _lookup(_DocumentChannel(document)))

    assert ContextDocument.from_metadata(enriched.metadata[METADATA_CONTEXT_DOCUMENT_KEY]) == document
    assert enriched.metadata["locale"] == "en"
    # The ledger snapshot task of the arrival message still holds the original dict; it must not gain the body.
    assert enriched.metadata is not msg.metadata
    assert METADATA_CONTEXT_DOCUMENT_KEY not in msg.metadata


async def test_an_overlong_body_is_cut_and_its_full_length_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enrichment, "MAX_CONTEXT_DOCUMENT_CHARS", 5)

    enriched = await enrich_context_document(_inbound(), _lookup(_DocumentChannel(ContextDocument.ready("0123456789"))))

    stored = ContextDocument.from_metadata(enriched.metadata[METADATA_CONTEXT_DOCUMENT_KEY])
    assert stored is not None
    assert (stored.markdown, stored.total_chars) == ("01234", 10)


@pytest.mark.parametrize("channel", [None, _DocumentChannel(None)], ids=["unknown-channel", "no-document"])
async def test_a_message_without_a_document_is_returned_as_is(channel: BaseChannel | None) -> None:
    msg = _inbound()

    assert await enrich_context_document(msg, _lookup(channel)) is msg


async def test_a_provider_fault_costs_the_document_and_not_the_turn(caplog: pytest.LogCaptureFixture) -> None:
    msg = _inbound()

    with caplog.at_level(logging.WARNING, logger="app.channels.routing.context_document"):
        result = await enrich_context_document(msg, _lookup(_DocumentChannel(fault=RuntimeError("boom"))))

    assert result is msg
    assert "context document" in caplog.text


async def test_a_channel_has_no_document_unless_it_overrides_the_hook() -> None:
    assert await _PlainChannel().read_context_document(_inbound()) is None


class _TurnHost(RouterExecutionMixin):
    """The execution mixin with the collaborators of one turn replaced by recorders."""

    def __init__(self, channel: BaseChannel) -> None:
        self._active_tasks: dict[str, _ActiveTask] = {}
        self._bus = MagicMock(get_channel=MagicMock(return_value=channel))
        self.streamed: InboundMessage | None = None

    async def _setup_message_effects(self, *_: object) -> None:
        return None

    async def _consume_executor_stream(
        self, msg: InboundMessage, *_: object, **__: object
    ) -> tuple[OutboundMessage | None, float]:
        self.streamed = msg
        return None, 0.0

    async def _deliver_agent_result(self, *_: object, **__: object) -> bool:
        return True

    def _resolve_live_placeholder_id(self, state_key: str) -> str | None:
        return None

    async def _cleanup_effects(self, *_: object) -> None:
        return None


def _context() -> _RouterExecutionContext:
    return _RouterExecutionContext(
        user_id="u1",
        state_key="plain:c1",
        chat_id="c1",
        message_id="m1",
        topic_ctx=None,
        exec_msg=_inbound(),
    )


async def test_the_agent_stream_gets_the_document_but_the_arrival_message_does_not() -> None:
    document = ContextDocument.ready("# Plan")
    host = _TurnHost(_DocumentChannel(document))
    ctx = _context()

    await host._execute_prepared_context(ctx, _AgentTurnScratch(), is_resume=False, inbound_had_voice=False)  # type: ignore[arg-type]

    assert host.streamed is not None
    assert ContextDocument.from_metadata(host.streamed.metadata[METADATA_CONTEXT_DOCUMENT_KEY]) == document
    assert METADATA_CONTEXT_DOCUMENT_KEY not in ctx.exec_msg.metadata


async def test_a_resumed_turn_does_not_ask_the_channel() -> None:
    channel = _DocumentChannel(ContextDocument.ready("# Plan"))
    host = _TurnHost(channel)
    ctx = _context()

    await host._execute_prepared_context(ctx, _AgentTurnScratch(), is_resume=True, inbound_had_voice=False)  # type: ignore[arg-type]

    assert channel.asked == []
    assert host.streamed is ctx.exec_msg
