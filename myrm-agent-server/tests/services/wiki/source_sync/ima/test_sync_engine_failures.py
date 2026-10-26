"""End-to-end slices when ima or the pipeline misbehaves: auth, rate limits, transient and permanent item failures, internal faults."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima import content as content_module
from app.services.wiki.source_sync.ima import engine
from app.services.wiki.source_sync.ima.engine import run_slice
from app.services.wiki.source_sync.ima.errors import (
    ImaAuthError,
    ImaError,
    ImaPermanentError,
    ImaRateLimitError,
    ImaTooLargeError,
    ImaTransientError,
)
from app.services.wiki.source_sync.ima.ledger import ImaLedger, LedgerRow, LedgerStatus
from app.services.wiki.source_sync.ima.models import ImaMediaInfo, ImaNote
from app.services.wiki.source_sync.ima.state import ImaSyncState, load_ima_state

from .support import (
    NOTE_MS,
    Downloads,
    FakeIma,
    entry,
    library,
    library_config,
    make_ctx,
    page,
    rows,
    run_pass,
    url,
)

pytestmark = pytest.mark.usefixtures("ima_db", "fast_importer")


async def test_auth_failure_stops_without_a_retry_and_a_later_clean_pass_clears_it(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail["list_knowledge_page"] = ImaAuthError("rejected")
    fake.fail["verify"] = ImaAuthError("rejected")

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


async def test_dead_web_pages_are_item_failures_and_do_not_stall_the_pass(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def crawl(url: str, *, allow_escalation: bool) -> None:
        return None

    monkeypatch.setattr(content_module.web_fetch_tools, "crawl", crawl)
    fake, state = FakeIma(), ImaSyncState()
    ids = [f"w{i}" for i in range(8)]
    fake.pages[("kb1", "")] = page(*(entry(media_id, f"Page {media_id}", media_type=2) for media_id in ids))
    fake.media = {
        media_id: ImaMediaInfo(media_type=2, url=f"https://example.com/{media_id}", headers={}, note_id="") for media_id in ids
    }

    outcome = await run_pass(fake, tmp_path, state)

    assert outcome.finished and outcome.error_kind == ""
    assert state.failure_streak == 0 and state.backfill_complete
    listed = (await rows(ima_db)).values()
    assert {(row.status, row.error_kind, row.attempts) for row in listed} == {(LedgerStatus.FAILED, "page_unavailable", 1)}


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
        assert await ImaLedger(DEFAULT_AGENT_SCOPE).retry_failed(db, ["kb1"]) == 1
        await db.commit()
    await run_pass(fake, tmp_path, state)
    assert (await rows(ima_db))["deep.md"].status == LedgerStatus.SYNCED


async def test_credential_rejection_on_a_library_item_stops_the_pool_and_keeps_the_row_pending(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], downloads: Downloads
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail["get_media_info"] = ImaAuthError("revoked")
    fake.fail["verify"] = ImaAuthError("revoked")

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


async def test_an_unexpected_failure_becomes_an_internal_backoff_and_clears_after_a_clean_slice(
    tmp_path: Path, downloads: Downloads, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, state = library(), ImaSyncState()

    async def broken(_ctx: object) -> None:
        raise RuntimeError("ledger exploded")

    with monkeypatch.context() as patched:
        patched.setattr(engine, "run_inventory", broken)
        outcome = await run_slice(make_ctx(fake, tmp_path, config=library_config(), state=state))

    assert outcome.error_kind == "internal" and outcome.retry_after_s is not None and outcome.retry_after_s >= 120
    assert state.last_error_kind == "internal" and state.failure_streak == 1
    assert "ledger exploded" not in repr(outcome)

    recovered = await run_pass(fake, tmp_path, state)
    assert recovered.finished and state.last_error_kind == "" and state.failure_streak == 0


async def test_cancellation_is_never_swallowed_by_the_internal_failure_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cancelled(_ctx: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(engine, "run_inventory", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await run_slice(make_ctx(library(), tmp_path, config=library_config(), state=ImaSyncState()))


async def test_a_ledger_failure_while_claiming_waits_for_in_flight_items_and_reports_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, completed = asyncio.Event(), []

    async def slow_download(target: str, headers: dict[str, str]) -> bytes:
        if target == url("m3"):
            await gate.wait()
        completed.append(target)
        return b"# Doc\n\nbody text"

    monkeypatch.setattr("app.services.wiki.source_sync.ima.content.download_media", slow_download)
    real_claim, claims = ImaLedger.claim, 0

    async def claim_once(self: ImaLedger, *args: object, **kwargs: object) -> list[LedgerRow]:
        nonlocal claims
        claims += 1
        if claims > 1:
            raise RuntimeError("database is locked")
        return await real_claim(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ImaLedger, "claim", claim_once)
    asyncio.get_running_loop().call_later(0.1, gate.set)
    state = ImaSyncState()

    outcome = await run_slice(make_ctx(library(), tmp_path, config=library_config(), state=state))

    assert outcome.error_kind == "internal" and state.last_error_kind == "internal"
    assert url("m3") in completed, "the slice must not return while a worker is still writing to the ledger"


@pytest.mark.parametrize(
    "failure", [ImaAuthError("refused"), ImaPermanentError("gone")], ids=["refused-by-ima", "failed-for-good"]
)
async def test_a_ledger_failure_while_recording_an_outcome_waits_for_in_flight_items_and_reports_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: ImaError
) -> None:
    gate, completed = asyncio.Event(), []

    async def slow_download(target: str, headers: dict[str, str]) -> bytes:
        if target == url("m3"):
            await gate.wait()
        completed.append(target)
        return b"# Doc\n\nbody text"

    async def locked(self: ImaLedger, *args: object, **kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr("app.services.wiki.source_sync.ima.content.download_media", slow_download)
    monkeypatch.setattr(ImaLedger, "record_failure", locked)
    asyncio.get_running_loop().call_later(0.1, gate.set)
    fake, state = library(), ImaSyncState()
    fake.fail_on[("get_media_info", "m1")] = failure

    outcome = await run_slice(make_ctx(fake, tmp_path, config=library_config(), state=state))

    assert outcome.error_kind == "internal" and state.last_error_kind == "internal"
    assert url("m3") in completed, "the slice must not return while a worker is still writing to the ledger"
