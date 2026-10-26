"""Scripted stand-in for the ima API, scripted downloads and builders for the engine-level tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from myrm_agent_harness.toolkits.wiki import WikiStructure
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima.client import NOTES_PAGE_LIMIT, ImaClient
from app.services.wiki.source_sync.ima.context import SyncContext
from app.services.wiki.source_sync.ima.engine import SliceOutcome, run_slice
from app.services.wiki.source_sync.ima.errors import ImaError
from app.services.wiki.source_sync.ima.identity import NOTES_LANE
from app.services.wiki.source_sync.ima.ledger import ImaLedger, LedgerRow
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
    """Scripted stand-in for ``ImaClient``: pages, media and notes are plain dicts; ``fail`` injects errors per method.

    The notes listing is cursor-paged like ima's: ``deleted_notes_head`` entries that ima still lists as deleted lead
    it (the parser drops them, so whole pages can come back empty), and ``after_notes_page`` runs once a page is served.
    """

    pages: dict[tuple[str, str], ImaListPage] = field(default_factory=dict)
    media: dict[str, ImaMediaInfo] = field(default_factory=dict)
    notes: list[ImaNote] = field(default_factory=list)
    note_text: dict[str, str] = field(default_factory=dict)
    fail: dict[str, ImaError] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    deleted_notes_head: int = 0
    after_notes_page: Callable[[], None] | None = None

    def _maybe_fail(self, method: str) -> None:
        self.calls.append(method)
        if method in self.fail:
            raise self.fail[method]

    async def list_knowledge_page(self, kb_id: str, *, folder_id: str = "", cursor: str = "") -> ImaListPage:
        self._maybe_fail("list_knowledge_page")
        return self.pages.get((kb_id, folder_id), ImaListPage())

    async def list_notes_page(self, *, cursor: str) -> ImaNotesPage:
        self._maybe_fail("list_notes_page")
        start = int(cursor or 0)
        end = start + NOTES_PAGE_LIMIT
        head = self.deleted_notes_head
        served = ImaNotesPage(
            notes=tuple(self.notes[max(start - head, 0) : max(end - head, 0)]),
            next_cursor=str(end),
            is_end=end >= head + len(self.notes),
        )
        if self.after_notes_page is not None:
            self.after_notes_page()
        return served

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


NOTE_MS = 1_700_000_000_000  # 2023-11-14


def note(index: int) -> ImaNote:
    return ImaNote(note_id=f"n{index}", title=f"Note {index}", folder_name="", modify_time=NOTE_MS)


class Downloads:
    """Scripted ``download_media``: bytes per URL, with optional per-URL errors."""

    def __init__(self) -> None:
        self.bodies: dict[str, bytes] = {}
        self.errors: dict[str, Exception] = {}
        self.calls: list[str] = []

    async def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.calls.append(url)
        if url in self.errors:
            raise self.errors.pop(url)
        return self.bodies.get(url, b"# Doc\n\nbody text")


def url(name: str) -> str:
    return f"https://bucket.cos.ap-guangzhou.myqcloud.com/{name}"


def library() -> FakeIma:
    """kb1: guide.md + an audio file at the root, deep.md in folder f1."""
    return FakeIma(
        pages={
            ("kb1", ""): page(entry("m1", "guide.md"), entry("m2", "talk.mp3", media_type=15), folders=(ImaFolder("f1", "Sub"),)),
            ("kb1", "f1"): page(entry("m3", "deep.md", parent="f1")),
        },
        media={
            "m1": file_info(7, url("m1")),
            "m2": ImaMediaInfo(media_type=15, url="", headers={}, note_id=""),
            "m3": file_info(7, url("m3")),
        },
    )


async def run_pass(fake: FakeIma, root: Path, state: ImaSyncState, config=None, *, max_slices: int = 8) -> SliceOutcome:
    config = config or library_config()
    outcome = await run_slice(make_ctx(fake, root, config=config, state=state))
    for _ in range(max_slices):
        if outcome.finished or outcome.error_kind:
            break
        outcome = await run_slice(make_ctx(fake, root, config=config, state=state))
    return outcome


async def rows(factory: async_sessionmaker[AsyncSession]) -> dict[str, LedgerRow]:
    async with factory() as db:
        listed = await ImaLedger(DEFAULT_AGENT_SCOPE).list_rows(db, containers=["kb1", "kb2", NOTES_LANE], limit=1000)
    return {row.title: row for row in listed}


def raw_file(root: Path, row: LedgerRow) -> Path:
    return root / "raw" / row.raw_path
