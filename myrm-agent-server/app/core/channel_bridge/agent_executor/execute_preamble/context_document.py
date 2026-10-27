"""Reference document of a channel turn, shown to the model after the user's message.

[INPUT]
- app.channels.types::ContextDocument, ContextDocumentStatus, METADATA_CONTEXT_DOCUMENT_KEY (POS: reference document contract)
- executor_helpers.agent_workspace::agent_workspace (POS: the directory the channel agent can read back)
- app.services.chat.context_bomb_guard::ContextBombDefenseService (POS: size guard that parks oversized text in a workspace file)
- myrm_agent_harness.agent.security.detection.content_boundary::wrap_tool_output (POS: boundary that marks text as reference data, not instructions)

[OUTPUT]
- attach_context_document(): the turn's query with its reference document appended

[POS]
Last step of the preamble before the agent runs. The block rides on the live turn only: the persisted history keeps the
user's message alone, so the document is read afresh each turn and never replayed from an earlier one.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.agent.security.detection.content_boundary import wrap_tool_output

from app.channels.types import (
    METADATA_CONTEXT_DOCUMENT_KEY,
    ContextDocument,
    ContextDocumentStatus,
    InboundMessage,
)
from app.core.channel_bridge.executor_helpers.agent_workspace import agent_workspace
from app.services.chat.context_bomb_guard import ContextBombDefenseService

logger = logging.getLogger(__name__)

_READ_FAILED = "reading it failed"
_WHY_NOT_ATTACHED: dict[ContextDocumentStatus, str] = {
    ContextDocumentStatus.DENIED: "no access to it",
    ContextDocumentStatus.TOO_LARGE: "it is too large to read",
    ContextDocumentStatus.UNSUPPORTED: "this kind of file cannot be read",
    ContextDocumentStatus.UNAVAILABLE: _READ_FAILED,
}


def _not_attached(reason: str) -> str:
    return (
        f"The document's text is not attached ({reason}). Answer from the rest of this message; "
        "if the question needs the document, say you cannot read it."
    )


def _size(document: ContextDocument) -> str:
    shown = len(document.markdown)
    if document.is_shortened:
        return f"first {shown:,} of {document.total_chars:,} characters"
    return f"{shown:,} characters"


async def _render(document: ContextDocument, chat_id: str) -> str:
    if document.status is not ContextDocumentStatus.READY:
        return _not_attached(_WHY_NOT_ATTACHED.get(document.status, _READ_FAILED))
    if not document.markdown.strip():
        return "The document is empty."

    workspace = agent_workspace(chat_id)
    if workspace is None:
        return _not_attached(_READ_FAILED)
    try:
        # The guard writes the file when the text is oversized; keep that I/O off the event loop.
        placed = await asyncio.to_thread(
            ContextBombDefenseService.process_incoming_content,
            document.markdown,
            chat_id=chat_id,
            workspace_root=workspace,
        )
    except OSError:
        logger.warning("Context document of chat %s could not be saved in the agent workspace", chat_id, exc_info=True)
        return _not_attached(_READ_FAILED)

    logger.info(
        "Channel turn context document: chat=%s chars=%d saved_to_file=%s", chat_id, len(document.markdown), placed.is_spilled
    )
    if placed.is_spilled:
        # No preview of the text: it is third-party content, so it only ever reaches the model through a boundary.
        return (
            f"The document's text ({_size(document)}) is saved at '{placed.spillover_path}', too long to show here. "
            "Read what you need with file_read_tool."
        )
    return f"Text of the document (Markdown, {_size(document)}):\n{wrap_tool_output(document.markdown)}"


async def attach_context_document(
    query: str | list[dict[str, object]],
    msg: InboundMessage,
    *,
    chat_id: str,
) -> str | list[dict[str, object]]:
    """``query`` followed by the document the turn's channel attached to ``msg``; unchanged when there is none.

    Only a text query takes the block: the turns that carry a reference document have no images.
    """
    document = ContextDocument.from_metadata(msg.metadata.get(METADATA_CONTEXT_DOCUMENT_KEY))
    if document is None or not isinstance(query, str):
        return query
    return f"{query}\n\n{await _render(document, chat_id)}"
