"""Reference-document enrichment for inbound messages.

[INPUT]
- channels.core.base::BaseChannel.read_context_document (POS: provider hook that reads the document a message is about)
- channels.types::METADATA_CONTEXT_DOCUMENT_KEY (POS: reference document contract)

[OUTPUT]
- enrich_context_document(): attach the document the message's channel read for it to the message metadata
- MAX_CONTEXT_DOCUMENT_CHARS: longest body kept

[POS]
Router enrichment step beside the media enrichments, run by ``RouterExecutionMixin`` right before the agent stream. It
cannot run earlier: the body can be hundreds of KB, and the inbound journal and the channel data-plane ledger both
serialize the message's metadata when they snapshot it.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.channels.types import METADATA_CONTEXT_DOCUMENT_KEY, InboundMessage

if TYPE_CHECKING:
    from app.channels.core.base import BaseChannel

type GetChannelFn = Callable[[str], BaseChannel | None]

logger = logging.getLogger(__name__)

# Same ceiling as the text extracted from an attached document, so a reference document weighs no more than one.
MAX_CONTEXT_DOCUMENT_CHARS = 200_000


async def enrich_context_document(msg: InboundMessage, get_channel_fn: GetChannelFn) -> InboundMessage:
    """``msg`` with the document its channel read for it, or ``msg`` itself when there is none."""
    channel = get_channel_fn(msg.channel)
    if channel is None:
        return msg
    try:
        document = await channel.read_context_document(msg)
        if document is None:
            return msg
        metadata = {**msg.metadata, METADATA_CONTEXT_DOCUMENT_KEY: document.clamped(MAX_CONTEXT_DOCUMENT_CHARS).as_metadata()}
    except Exception:
        # A provider fault costs the turn its reference document, never the turn itself.
        logger.warning("Reading the context document of %s/%s failed", msg.channel, msg.chat_id, exc_info=True)
        return msg
    # A new dict, never an in-place edit: the ledger snapshot task still holds the original one.
    return dataclasses.replace(msg, metadata=metadata)
