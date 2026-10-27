"""Reference document that a channel attaches to a turn.

[INPUT]
- (none: pure types, no I/O)

[OUTPUT]
- METADATA_CONTEXT_DOCUMENT_KEY: ``InboundMessage.metadata`` key that carries the document to the agent executor
- ContextDocumentStatus: whether the body could be read and, when not, why
- ContextDocument: the body (Markdown) with its status; round-trips through message metadata

[POS]
Channel-agnostic contract between a provider that can read the document a message is about and the agent executor
that shows it to the model.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import StrEnum

METADATA_CONTEXT_DOCUMENT_KEY = "context_document"


class ContextDocumentStatus(StrEnum):
    """Outcome of reading the document."""

    READY = "ready"
    DENIED = "denied"
    TOO_LARGE = "too_large"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ContextDocument:
    """A document body, or the reason there is none.

    ``total_chars`` is the body length before ``clamped`` shortened it.
    """

    status: ContextDocumentStatus
    markdown: str = ""
    total_chars: int = 0

    @classmethod
    def ready(cls, markdown: str) -> ContextDocument:
        return cls(ContextDocumentStatus.READY, markdown, len(markdown))

    @property
    def is_shortened(self) -> bool:
        return len(self.markdown) < self.total_chars

    def clamped(self, max_chars: int) -> ContextDocument:
        """The document with its body cut to ``max_chars`` (``self`` when it already fits)."""
        if len(self.markdown) <= max_chars:
            return self
        return dataclasses.replace(self, markdown=self.markdown[:max_chars])

    def as_metadata(self) -> dict[str, object]:
        """Plain-data form for ``InboundMessage.metadata``."""
        return {"status": self.status.value, "markdown": self.markdown, "total_chars": self.total_chars}

    @classmethod
    def from_metadata(cls, raw: object) -> ContextDocument | None:
        """Rebuild from ``as_metadata`` output; None for anything else."""
        if not isinstance(raw, dict):
            return None
        status, markdown, total_chars = raw.get("status"), raw.get("markdown"), raw.get("total_chars")
        if not (isinstance(status, str) and isinstance(markdown, str) and isinstance(total_chars, int)):
            return None
        try:
            return cls(ContextDocumentStatus(status), markdown, total_chars)
        except ValueError:
            return None
