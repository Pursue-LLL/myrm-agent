"""Scripted stand-in for the ima API and builders for the engine-level tests."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima.client import ImaClient
from app.services.wiki.source_sync.ima.context import SyncContext
from app.services.wiki.source_sync.ima.errors import ImaError
from app.services.wiki.source_sync.ima.ledger import ImaLedger
from app.services.wiki.source_sync.ima.models import (
    ImaEntry,
    ImaFolder,
    ImaListPage,
    ImaMediaInfo,
    ImaNote,
    ImaNotesPage,
)
from app.services.wiki.source_sync.ima.state import ImaKbSelection, ImaSyncConfig, ImaSyncState


@dataclass
class FakeIma:
    """Scripted stand-in for ``ImaClient``: pages, media and notes are plain dicts; ``fail`` injects errors per method."""

    pages: dict[tuple[str, str], ImaListPage] = field(default_factory=dict)
    media: dict[str, ImaMediaInfo] = field(default_factory=dict)
    notes: list[ImaNote] = field(default_factory=list)
    note_text: dict[str, str] = field(default_factory=dict)
    fail: dict[str, ImaError] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def _maybe_fail(self, method: str) -> None:
        self.calls.append(method)
        if method in self.fail:
            raise self.fail[method]

    async def list_knowledge_page(self, kb_id: str, *, folder_id: str = "", cursor: str = "") -> ImaListPage:
        self._maybe_fail("list_knowledge_page")
        return self.pages.get((kb_id, folder_id), ImaListPage())

    async def list_notes_page(self, *, start: int) -> ImaNotesPage:
        self._maybe_fail("list_notes_page")
        return ImaNotesPage(notes=tuple(self.notes[start : start + 50]), is_end=start + 50 >= len(self.notes))

    async def get_media_info(self, media_id: str) -> ImaMediaInfo:
        self._maybe_fail("get_media_info")
        return self.media[media_id]

    async def get_note_text(self, note_id: str) -> str:
        self._maybe_fail("get_note_text")
        return self.note_text.get(note_id, "")


def entry(media_id: str, title: str, media_type: int | None = 7, parent: str = "") -> ImaEntry:
    return ImaEntry(media_id=media_id, title=title, parent_folder_id=parent, media_type=media_type)


def page(*items: ImaEntry, folders: tuple[ImaFolder, ...] = ()) -> ImaListPage:
    return ImaListPage(items=tuple(items), folders=folders, next_cursor="", is_end=True)


def file_info(media_type: int = 7, url: str = "https://x.cos.ap-guangzhou.myqcloud.com/f") -> ImaMediaInfo:
    return ImaMediaInfo(media_type=media_type, url=url, headers={}, note_id="")


def as_client(fake: FakeIma) -> ImaClient:
    """``FakeIma`` implements exactly the methods the sync lane calls on ``ImaClient``."""
    return cast(ImaClient, fake)


def make_ctx(
    fake: FakeIma,
    root: Path,
    *,
    config: ImaSyncConfig,
    state: ImaSyncState,
    budget_s: float = 60.0,
) -> SyncContext:
    return SyncContext(
        agent_id=None,
        client=as_client(fake),
        structure=WikiStructure(base_dir=root),
        config=config,
        state=state,
        ledger=ImaLedger(DEFAULT_AGENT_SCOPE),
        deadline=time.monotonic() + budget_s,
    )


def library_config(*, notes: bool = False, kb_ids: tuple[str, ...] = ("kb1",)) -> ImaSyncConfig:
    return ImaSyncConfig(knowledge_bases=[ImaKbSelection(id=kb_id, name=f"Lib {kb_id}") for kb_id in kb_ids], include_notes=notes)
