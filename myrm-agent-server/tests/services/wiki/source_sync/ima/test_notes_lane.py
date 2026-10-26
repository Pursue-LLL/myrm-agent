"""The notes lane of the inventory: cursor paging, resumption across slices, and never judging notes deleted from a listing that did not finish."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.source_sync.ima.client import NOTES_PAGE_LIMIT, ImaClient
from app.services.wiki.source_sync.ima.engine import run_slice
from app.services.wiki.source_sync.ima.errors import ImaPermanentError
from app.services.wiki.source_sync.ima.identity import NOTES_LANE
from app.services.wiki.source_sync.ima.inventory import begin_generation, run_inventory
from app.services.wiki.source_sync.ima.ledger import LedgerStatus
from app.services.wiki.source_sync.ima.models import ImaCredentials, ImaNotesPage
from app.services.wiki.source_sync.ima.state import ImaSyncState, load_ima_state
from app.services.wiki.source_sync.ima.transport import ImaTransport

from .support import FakeIma, library_config, make_ctx, note, rows, run_pass

pytestmark = pytest.mark.usefixtures("ima_db", "fast_importer", "downloads")


def _fake(count: int) -> FakeIma:
    notes = [note(index) for index in range(count)]
    return FakeIma(notes=notes, note_text={item.note_id: f"body of {item.title}" for item in notes})


@dataclass
class _StalledNotes(FakeIma):
    """A notes listing that keeps claiming there is more and offers ``stall_cursor`` as the way on."""

    stall_cursor: str = ""

    async def list_notes_page(self, *, cursor: str) -> ImaNotesPage:
        self._maybe_fail("list_notes_page")
        return ImaNotesPage(notes=tuple(self.notes[:1]), next_cursor=self.stall_cursor, is_end=False)


async def _statuses(ima_db: async_sessionmaker[AsyncSession]) -> set[str]:
    return {str(row.status) for row in (await rows(ima_db)).values()}


async def test_the_walk_goes_past_pages_that_are_empty_once_deleted_notes_are_dropped(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state, config = _fake(3), ImaSyncState(), library_config(notes=True, kb_ids=())
    await run_pass(fake, tmp_path, state, config)
    assert await _statuses(ima_db) == {LedgerStatus.SYNCED}

    fake.deleted_notes_head = 3 * NOTES_PAGE_LIMIT  # the listing now opens with three pages of deleted notes
    fake.calls.clear()
    outcome = await run_pass(fake, tmp_path, state, config)

    assert outcome.finished and fake.calls.count("list_notes_page") == 4
    assert await _statuses(ima_db) == {LedgerStatus.SYNCED}


async def test_the_walk_resumes_from_its_persisted_cursor_in_the_next_slice(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, config = _fake(NOTES_PAGE_LIMIT + 3), library_config(notes=True, kb_ids=())
    ctx = make_ctx(fake, tmp_path, config=config, state=ImaSyncState())
    fake.after_notes_page = lambda: setattr(ctx, "deadline", 0.0)  # the time box ends once the first page is in

    first = await run_slice(ctx)

    assert not first.finished
    async with ima_db() as db:
        restored = await load_ima_state(db, agent_id=None)
    assert restored.phase == "inventory" and restored.notes_cursor
    assert len(await rows(ima_db)) == NOTES_PAGE_LIMIT

    fake.after_notes_page = None
    outcome = await run_pass(fake, tmp_path, restored, config)

    assert outcome.finished and fake.calls.count("list_notes_page") == 2
    assert len(await rows(ima_db)) == NOTES_PAGE_LIMIT + 3


@pytest.mark.parametrize("stall_cursor", ["", "same"], ids=["no-cursor", "repeated-cursor"])
async def test_a_listing_that_stalls_before_its_end_is_never_taken_for_complete(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], stall_cursor: str
) -> None:
    config, state = library_config(notes=True, kb_ids=()), ImaSyncState()
    await run_pass(_fake(2), tmp_path, state, config)

    stalled = _StalledNotes(notes=[note(0)], note_text={"n0": "body of Note 0"}, stall_cursor=stall_cursor)
    outcome = await run_pass(stalled, tmp_path, state, config)

    # Note 1 was not listed, but the listing never reached its end, so it must not be judged deleted.
    assert outcome.finished and state.failed_containers == [NOTES_LANE]
    assert await _statuses(ima_db) == {LedgerStatus.SYNCED}


async def test_a_page_in_an_unrecognized_shape_fails_the_lane_without_judging_any_note_deleted(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, config, state = _fake(2), library_config(notes=True, kb_ids=()), ImaSyncState()
    await run_pass(fake, tmp_path, state, config)

    fake.fail["list_notes_page"] = ImaPermanentError("ima returned notes in an unrecognized shape")
    outcome = await run_pass(fake, tmp_path, state, config)

    assert outcome.finished and state.failed_containers == [NOTES_LANE]
    assert await _statuses(ima_db) == {LedgerStatus.SYNCED}


async def test_wire_pages_of_only_deleted_notes_do_not_end_the_walk(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    def deleted(doc_id: str) -> dict[str, object]:
        return {"basic_info": {"basic_info": {"docid": doc_id, "status": 1}}}

    pages: dict[str, dict[str, object]] = {
        "": {"note_book_list": [deleted("d1"), deleted("d2")], "next_cursor": "p2", "is_end": False},
        "p2": {
            "note_book_list": [
                {"basic_info": {"basic_info": {"docid": "n1", "title": "Plan", "folder_name": "Work", "modify_time": 5}}}
            ],
            "next_cursor": "",
            "is_end": True,
        },
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = json.loads(request.content)["cursor"]
        requested.append(cursor)
        return httpx.Response(200, json={"retcode": 0, "data": pages[cursor]})

    client = ImaClient(ImaTransport(ImaCredentials(client_id="c", api_key="k"), transport=httpx.MockTransport(handler)))
    state = ImaSyncState()
    ctx = replace(make_ctx(FakeIma(), tmp_path, config=library_config(notes=True, kb_ids=()), state=state), client=client)
    ctx.deadline = time.monotonic() + 60

    await begin_generation(ctx)
    await run_inventory(ctx)

    assert requested == ["", "p2"]
    assert state.phase == "fetch" and state.notes_cursor is None and state.failed_containers == []
    assert {title: row.folder_path for title, row in (await rows(ima_db)).items()} == {"Plan": "Work"}
