"""End-to-end slices over the real ledger, state store and raw gate, with a scripted ima API."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima import importer
from app.services.wiki.source_sync.ima.engine import SliceOutcome, run_slice
from app.services.wiki.source_sync.ima.errors import (
    ImaAuthError,
    ImaPermanentError,
    ImaRateLimitError,
    ImaTooLargeError,
    ImaTransientError,
)
from app.services.wiki.source_sync.ima.ledger import ImaLedger, LedgerRow, LedgerStatus
from app.services.wiki.source_sync.ima.models import ImaFolder, ImaMediaInfo, ImaNote
from app.services.wiki.source_sync.ima.state import ImaSyncState, load_ima_state, save_ima_state

from .support import FakeIma, entry, file_info, library_config, make_ctx, page

pytestmark = pytest.mark.usefixtures("ima_db")

NOTE_MS = 1_700_000_000_000  # 2023-11-14


@pytest.fixture(autouse=True)
def _fast_importer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer, "_PACE_S", 0.0)


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


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> Downloads:
    fake = Downloads()
    monkeypatch.setattr("app.services.wiki.source_sync.ima.content.download_media", fake)
    return fake


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
        listed = await ImaLedger(DEFAULT_AGENT_SCOPE).list_rows(db, limit=1000)
    return {row.title: row for row in listed}


def raw_file(root: Path, row: LedgerRow) -> Path:
    return root / "raw" / row.raw_path


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
    assert by_title["Plan"].fidelity == "partial" and "plain_text" in by_title["Plan"].fidelity_notes
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


async def test_auth_failure_stops_without_a_retry_and_a_later_clean_pass_clears_it(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail["list_knowledge_page"] = ImaAuthError("rejected")

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.error_kind == "auth" and outcome.retry_after_s is None and not outcome.finished
    async with ima_db() as db:
        assert (await load_ima_state(db, agent_id=None)).needs_reauth is True

    fake.fail.clear()
    assert (await run_pass(fake, tmp_path, state)).finished
    assert state.needs_reauth is False and state.last_error_kind == ""


@pytest.mark.parametrize(("server_hint", "expected"), [(5.0, 30.0), (300.0, 300.0), (None, 30.0)])
async def test_rate_limit_pauses_for_the_longer_of_the_hint_and_the_floor(
    tmp_path: Path, downloads: Downloads, server_hint: float | None, expected: float
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail["list_knowledge_page"] = ImaRateLimitError("slow down", retry_after_s=server_hint)

    outcome = await run_slice(make_ctx(fake, tmp_path, config=library_config(), state=state))

    assert outcome.error_kind == "rate_limit" and outcome.retry_after_s == expected


async def test_transient_failures_back_off_exponentially_and_recover(tmp_path: Path, downloads: Downloads) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail["list_knowledge_page"] = ImaTransientError("network")
    config = library_config()

    first = await run_slice(make_ctx(fake, tmp_path, config=config, state=state))
    second = await run_slice(make_ctx(fake, tmp_path, config=config, state=state))
    assert (first.retry_after_s, second.retry_after_s) == (240.0, 480.0)
    assert state.failure_streak == 2 and state.last_error_kind == "transient"

    fake.fail.clear()
    assert (await run_pass(fake, tmp_path, state, config)).finished
    assert state.failure_streak == 0 and state.last_error_kind == ""


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


async def test_each_item_failure_has_its_own_outcome_without_aborting_the_pass(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    downloads.errors[url("m1")] = ImaTooLargeError("too big")
    downloads.errors[url("m3")] = ImaTransientError("flaky")

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.finished
    by_title = await rows(ima_db)
    assert by_title["guide.md"].status == LedgerStatus.TOO_LARGE
    assert by_title["deep.md"].status == LedgerStatus.FAILED and by_title["deep.md"].attempts == 1
    assert by_title["deep.md"].error_kind == "transient"

    assert (await run_pass(fake, tmp_path, state)).finished
    assert (await rows(ima_db))["deep.md"].status == LedgerStatus.SYNCED


async def test_permanent_item_failure_exhausts_its_budget_until_the_user_retries(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    downloads.errors[url("m3")] = ImaPermanentError("gone")
    await run_pass(fake, tmp_path, state)
    assert (await rows(ima_db))["deep.md"].attempts == 3

    downloads.calls.clear()
    await run_pass(fake, tmp_path, state)
    assert url("m3") not in downloads.calls

    async with ima_db() as db:
        assert await ImaLedger(DEFAULT_AGENT_SCOPE).retry_failed(db) == 1
        await db.commit()
    await run_pass(fake, tmp_path, state)
    assert (await rows(ima_db))["deep.md"].status == LedgerStatus.SYNCED


async def test_credential_rejection_on_a_library_item_stops_the_pool_and_keeps_the_row_pending(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail["get_media_info"] = ImaAuthError("revoked")

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.error_kind == "auth" and state.needs_reauth
    assert all(row.status != LedgerStatus.FAILED for row in (await rows(ima_db)).values())


async def test_missing_notes_permission_fails_only_the_notes_and_the_pass_still_finishes(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    fake.notes = [ImaNote(note_id="n1", title="Plan", folder_name="", modify_time=NOTE_MS)]
    fake.fail["get_note_text"] = ImaAuthError("no notes permission")

    outcome = await run_pass(fake, tmp_path, state, library_config(notes=True))

    assert outcome.finished
    plan = (await rows(ima_db))["Plan"]
    assert plan.status == LedgerStatus.FAILED and plan.error_kind == "notes_permission"


async def test_state_survives_a_restart_between_slices(tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]) -> None:
    state = ImaSyncState(phase="fetch", generation=4, backfill_complete=True)
    async with ima_db() as db:
        await save_ima_state(db, state, agent_id=None)
    async with ima_db() as db:
        assert await load_ima_state(db, agent_id=None) == state
