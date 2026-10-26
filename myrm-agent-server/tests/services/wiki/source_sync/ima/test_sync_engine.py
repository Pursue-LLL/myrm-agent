"""End-to-end slices over the real ledger, state store and raw gate, with a scripted ima API: import, change tracking and resumption."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima.engine import run_slice
from app.services.wiki.source_sync.ima.errors import (
    ImaPermanentError,
)
from app.services.wiki.source_sync.ima.ledger import ImaLedger, LedgerStatus
from app.services.wiki.source_sync.ima.models import ImaFolder, ImaMediaInfo, ImaNote
from app.services.wiki.source_sync.ima.state import ImaSyncState, load_ima_state, save_ima_state

from .support import (
    NOTE_MS,
    Downloads,
    FakeIma,
    entry,
    file_info,
    library,
    library_config,
    make_ctx,
    note,
    page,
    raw_file,
    rows,
    run_pass,
    url,
)

pytestmark = pytest.mark.usefixtures("ima_db", "fast_importer")


async def test_first_pass_imports_documents_folders_and_notes(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake = library()
    fake.notes = [ImaNote(note_id="n1", title="Plan", folder_name="Work", modify_time=NOTE_MS)]
    fake.note_text = {"n1": "note body text"}
    state = ImaSyncState()

    outcome = await run_pass(fake, tmp_path, state, library_config(notes=True))

    assert outcome.finished and outcome.retry_after_s is None
    assert state.phase == "idle" and state.backfill_complete and state.generation == 1
    by_title = await rows(ima_db)
    assert {title: row.status for title, row in by_title.items()} == {
        "guide.md": LedgerStatus.SYNCED,
        "deep.md": LedgerStatus.SYNCED,
        "talk.mp3": LedgerStatus.UNSUPPORTED,
        "Plan": LedgerStatus.SYNCED,
    }
    assert by_title["talk.mp3"].error_kind == "unsupported_type"
    assert by_title["deep.md"].folder_path == "Sub"
    guide = raw_file(tmp_path, by_title["guide.md"]).read_text(encoding="utf-8")
    assert 'source: "ima"' in guide and "body text" in guide and "Lib kb1" in guide
    note = raw_file(tmp_path, by_title["Plan"]).read_text(encoding="utf-8")
    assert 'modified: "2023-11-14"' in note and "note body text" in note
    assert by_title["Plan"].fidelity == "full" and by_title["Plan"].fidelity_notes == ()
    assert by_title["guide.md"].fidelity == "full"


async def test_unchanged_second_pass_downloads_nothing_and_publishes_nothing(tmp_path: Path, downloads: Downloads) -> None:
    fake, state = library(), ImaSyncState()
    await run_pass(fake, tmp_path, state)
    downloads.calls.clear()
    fake.calls.clear()

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.finished and state.generation == 2
    assert downloads.calls == [] and "get_media_info" not in fake.calls
    assert outcome.generation_total == 0


async def test_replaced_file_is_superseded_and_unchanged_ones_are_left_alone(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    await run_pass(fake, tmp_path, state)
    before = await rows(ima_db)

    fake.pages[("kb1", "")] = page(
        entry("m1b", "guide.md"), entry("m2", "talk.mp3", media_type=15), folders=(ImaFolder("f1", "Sub"),)
    )
    fake.media["m1b"] = file_info(7, url("m1b"))
    downloads.bodies[url("m1b")] = b"# Doc\n\nsecond version"
    downloads.calls.clear()
    outcome = await run_pass(fake, tmp_path, state)

    after = await rows(ima_db)
    assert outcome.generation_total == 1
    assert downloads.calls == [url("m1b")]
    assert "second version" in raw_file(tmp_path, after["guide.md"]).read_text(encoding="utf-8")
    assert after["guide.md"].raw_path == before["guide.md"].raw_path
    assert after["guide.md"].synced_version == "m1b"


async def test_remote_deletion_is_recorded_but_the_local_copy_is_kept(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    await run_pass(fake, tmp_path, state)
    fake.pages[("kb1", "f1")] = page()

    await run_pass(fake, tmp_path, state)

    deep = (await rows(ima_db))["deep.md"]
    assert deep.status == LedgerStatus.REMOTE_DELETED
    assert raw_file(tmp_path, deep).is_file()


async def test_a_partial_inventory_never_marks_missing_items_as_deleted(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    await run_pass(fake, tmp_path, state)
    fake.fail["list_knowledge_page"] = ImaPermanentError("library unavailable")

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.finished and "kb1" in state.failed_containers
    assert all(row.status != LedgerStatus.REMOTE_DELETED for row in (await rows(ima_db)).values())


async def test_user_deleted_raw_file_is_dismissed_and_never_comes_back(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    await run_pass(fake, tmp_path, state)
    guide = (await rows(ima_db))["guide.md"]
    raw_file(tmp_path, guide).unlink()
    downloads.calls.clear()

    await run_pass(fake, tmp_path, state)
    await run_pass(fake, tmp_path, state)

    assert (await rows(ima_db))["guide.md"].status == LedgerStatus.DISMISSED
    assert not raw_file(tmp_path, guide).exists()
    assert url("m1") not in downloads.calls


async def test_slice_out_of_time_resumes_from_the_persisted_cursor(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    config = library_config()

    stalled = await run_slice(make_ctx(fake, tmp_path, config=config, state=state, budget_s=-1))
    assert not stalled.finished and stalled.retry_after_s == 5.0
    assert state.phase == "inventory" and [task.kb_id for task in state.queue] == ["kb1"]

    async with ima_db() as db:
        restored = await load_ima_state(db, agent_id=None)
    assert restored.phase == "inventory" and restored.queue == state.queue

    outcome = await run_pass(fake, tmp_path, restored, config)
    assert outcome.finished
    assert (await rows(ima_db))["deep.md"].status == LedgerStatus.SYNCED


async def test_changing_the_selection_restarts_the_inventory_and_holds_back_auto_compile(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    await run_pass(fake, tmp_path, state)
    assert state.backfill_complete and state.generation == 1
    fake.pages[("kb2", "")] = page(entry("x1", "other.md"))
    fake.media["x1"] = file_info(7, url("x1"))

    config = library_config(kb_ids=("kb1", "kb2"))
    first = await run_slice(make_ctx(fake, tmp_path, config=config, state=state, budget_s=-1))

    assert not first.finished and state.generation == 2 and state.backfill_complete is False
    assert (await run_pass(fake, tmp_path, state, config)).finished
    assert (await rows(ima_db))["other.md"].status == LedgerStatus.SYNCED


async def test_a_note_carrying_a_credential_is_stored_redacted_and_flagged_partial(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    secret = "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcd"
    fake = FakeIma(notes=[note(1)], note_text={"n1": f"deploy with OPENAI_API_KEY={secret}"})

    outcome = await run_pass(fake, tmp_path, ImaSyncState(), library_config(notes=True, kb_ids=()))

    assert outcome.finished
    row = (await rows(ima_db))["Note 1"]
    assert row.status == LedgerStatus.SYNCED and row.fidelity == "partial" and "redacted" in row.fidelity_notes
    stored = raw_file(tmp_path, row).read_text(encoding="utf-8")
    assert secret not in stored and "[REDACTED:" in stored


async def test_notes_lane_is_skipped_entirely_when_disabled(tmp_path: Path, downloads: Downloads) -> None:
    fake, state = library(), ImaSyncState()
    fake.notes = [ImaNote(note_id="n1", title="Plan", folder_name="", modify_time=NOTE_MS)]

    await run_pass(fake, tmp_path, state, library_config(notes=False))

    assert "list_notes_page" not in fake.calls


async def test_a_linked_note_already_covered_by_the_notes_lane_is_not_imported_twice(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    fake.pages[("kb1", "")] = page(entry("lnk", "Linked note", media_type=11))
    fake.pages[("kb1", "f1")] = page()
    fake.media["lnk"] = ImaMediaInfo(media_type=11, url="", headers={}, note_id="n1")
    fake.notes = [ImaNote(note_id="n1", title="Plan", folder_name="", modify_time=NOTE_MS)]
    fake.note_text = {"n1": "shared body"}

    await run_pass(fake, tmp_path, state, library_config(notes=True))

    by_title = await rows(ima_db)
    assert by_title["Linked note"].status == LedgerStatus.DUPLICATE
    assert by_title["Plan"].status == LedgerStatus.SYNCED


async def test_state_survives_a_restart_between_slices(tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]) -> None:
    state = ImaSyncState(phase="fetch", generation=4, backfill_complete=True)
    async with ima_db() as db:
        await save_ima_state(db, state, agent_id=None)
    async with ima_db() as db:
        assert await load_ima_state(db, agent_id=None) == state


async def test_same_titled_documents_in_one_folder_are_both_imported_and_stay_stable(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake = FakeIma(
        pages={("kb1", ""): page(entry("m1", "Home.md"), entry("m2", "Home.md"), entry("m3", "Home.md"))},
        media={media_id: file_info(7, url(media_id)) for media_id in ("m1", "m2", "m3")},
    )
    downloads.bodies = {url("m1"): b"# one\n\nfirst", url("m2"): b"# two\n\nsecond", url("m3"): b"# three\n\nthird"}
    state = ImaSyncState()

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.finished and outcome.error_kind == ""
    async with ima_db() as db:
        listed = await ImaLedger(DEFAULT_AGENT_SCOPE).list_rows(db, containers=["kb1"])
    assert sorted(row.remote_id for row in listed) == ["m1", "m2", "m3"]
    assert {row.status for row in listed} == {LedgerStatus.SYNCED}
    assert len({row.raw_path for row in listed}) == 3
    texts = {raw_file(tmp_path, row).read_text(encoding="utf-8") for row in listed}
    assert any("first" in text for text in texts) and any("third" in text for text in texts)

    downloads.calls.clear()
    again = await run_pass(fake, tmp_path, state)
    assert again.finished and again.generation_total == 0 and downloads.calls == []
