"""Sandbox persistence of web_fetch's full text, plus the guide that points at the omitted parts.

Reuses UECD (Unified Evicted Content Delivery) so the product evicted-file API
and GUI drawer work without new endpoints.

Architecture: toolkits/ must not import agent/. The evicted-content helpers live
in agent.context_management.infra, so we accept them via callback injection
(set by the middleware layer at session start) rather than a static import.

[INPUT]
- processing.full_content_delivery::ReadRange, clamp_read_ranges (POS: Omitted-line ranges of the stored copy and their clamp to a capped copy)

[OUTPUT]
- StoredFullText, store_full_text, emit_web_fetch_evicted_ref
- set_evicted_content_callbacks (injection point for agent layer)

[POS]
Toolkit-layer persistence helper for web_fetch_tool full-content mode only.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

from myrm_agent_harness.toolkits.web_fetch.processing.full_content_delivery import ReadRange, clamp_read_ranges

logger = logging.getLogger(__name__)


class PersistedFile(Protocol):
    """What the agent layer reports after persisting text under the evicted directory."""

    @property
    def evicted_ref(self) -> str | None: ...

    @property
    def rel_path(self) -> str | None: ...

    @property
    def stored_chars(self) -> int: ...

    @property
    def total_lines(self) -> int: ...

    @property
    def storage_truncated(self) -> bool: ...

    @property
    def original_chars(self) -> int: ...


@dataclass(frozen=True, slots=True)
class _EvictedCallbacks:
    """Callback bundle injected by the agent layer."""

    persist: Callable[..., Awaitable[PersistedFile]]
    build_footer: Callable[..., str]
    emit_ref: Callable[..., Awaitable[None]]


_evicted_callbacks_var: ContextVar[_EvictedCallbacks | None] = ContextVar("web_fetch_evicted_callbacks", default=None)


def set_evicted_content_callbacks(
    *,
    persist_fn: Callable[..., Awaitable[PersistedFile]],
    build_footer_fn: Callable[..., str],
    emit_ref_fn: Callable[..., Awaitable[None]],
) -> None:
    """Inject evicted-content callbacks from the agent/middleware layer."""
    _evicted_callbacks_var.set(
        _EvictedCallbacks(persist=persist_fn, build_footer=build_footer_fn, emit_ref=emit_ref_fn)
    )


@dataclass(frozen=True, slots=True)
class StoredFullText:
    """The persisted copy, and the trusted text that tells the model which lines hold the omitted parts."""

    evicted_ref: str
    stored_chars: int
    total_lines: int
    storage_truncated: bool
    read_guide: str


async def store_full_text(text: str, read_ranges: Sequence[ReadRange]) -> StoredFullText | None:
    """Persist ``text`` and build the read guide; ``None`` when nothing could be persisted.

    The caller then delivers the cut text without any promise of a file to read. The persist callback only absorbs
    ``OSError``; text the encoder rejects (a lone surrogate) or a path with a null byte raises ``ValueError``, which
    must not fail the whole fetch.
    """
    callbacks = _evicted_callbacks_var.get()
    if callbacks is None:
        return None
    try:
        persisted = await callbacks.persist(text, "web_fetch", ext="md")
    except (OSError, ValueError) as exc:
        logger.warning("web_fetch full text was not persisted: %s", exc)
        return None
    if not persisted.evicted_ref or not persisted.rel_path:
        return None

    guide = callbacks.build_footer(
        evicted_basename=persisted.evicted_ref,
        rel_path=persisted.rel_path,
        storage_truncated=persisted.storage_truncated,
        original_chars=persisted.original_chars,
        stored_chars=persisted.stored_chars,
        read_ranges=clamp_read_ranges(read_ranges, persisted.total_lines),
    )
    return StoredFullText(
        evicted_ref=persisted.evicted_ref,
        stored_chars=persisted.stored_chars,
        total_lines=persisted.total_lines,
        storage_truncated=persisted.storage_truncated,
        read_guide=guide,
    )


async def emit_web_fetch_evicted_ref(
    evicted_ref: str,
    *,
    stored_chars: int | None = None,
    total_lines: int | None = None,
    storage_truncated: bool = False,
) -> None:
    """Notify the GUI that full fetch content is available in the evicted drawer."""
    cbs = _evicted_callbacks_var.get()
    if cbs is not None:
        await cbs.emit_ref(
            evicted_ref,
            stored_chars=stored_chars,
            total_lines=total_lines,
            storage_truncated=storage_truncated,
        )
