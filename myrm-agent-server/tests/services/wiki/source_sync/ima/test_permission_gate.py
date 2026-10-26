"""A refused request is not always a revoked key: ima refuses a resource the key may not read the same way.

The slice asks once whether the key still works (``SyncContext.require_valid_key``). A bad key stops everything and asks
for a reconnect; a working key only fences off the library, note or item ima refused. Failure details reach the log as
one summary line per slice, never as titles or bodies.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima.engine import run_slice
from app.services.wiki.source_sync.ima.errors import ImaAuthError, ImaError, ImaRateLimitError, ImaTransientError
from app.services.wiki.source_sync.ima.ledger import MAX_ATTEMPTS, ImaLedger, LedgerStatus
from app.services.wiki.source_sync.ima.state import ImaSyncState
from app.services.wiki.source_sync.ima.transport import unwrap_envelope

from .support import Downloads, FakeIma, entry, file_info, library, library_config, make_ctx, note, page, rows, run_pass, url

pytestmark = pytest.mark.usefixtures("ima_db", "fast_importer", "downloads")

TWO_LIBRARIES = library_config(kb_ids=("kb1", "kb2"))
NOTES_ONLY = library_config(notes=True, kb_ids=())


def envelope_error(code: int, message: str = "") -> ImaError:
    """The exception the transport raises when ima answers with ``code``."""
    with pytest.raises(ImaError) as caught:
        unwrap_envelope({"retcode": code, "errmsg": message}, status_code=200)
    return caught.value


def two_libraries() -> FakeIma:
    return FakeIma(
        pages={
            ("kb1", ""): page(entry("m1", "one.md"), entry("m2", "two.md")),
            ("kb2", ""): page(entry("m3", "three.md"), entry("m4", "four.md")),
        },
        media={media_id: file_info(7, url(media_id)) for media_id in ("m1", "m2", "m3", "m4")},
    )


def crowded_library(size: int = 9) -> FakeIma:
    """One library of ``size`` documents named ``m0.md`` ... ``m{size-1}.md``."""
    ids = [f"m{index}" for index in range(size)]
    return FakeIma(
        pages={("kb1", ""): page(*(entry(media_id, f"{media_id}.md") for media_id in ids))},
        media={media_id: file_info(7, url(media_id)) for media_id in ids},
    )


def notes_only(count: int = 3) -> FakeIma:
    notes = [note(index) for index in range(count)]
    return FakeIma(notes=notes, note_text={item.note_id: f"body of {item.title}" for item in notes})


async def statuses(ima_db: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    return {title: str(row.status) for title, row in (await rows(ima_db)).items()}


async def retry_failed(ima_db: async_sessionmaker[AsyncSession], containers: list[str]) -> int:
    async with ima_db() as db:
        count = await ImaLedger(DEFAULT_AGENT_SCOPE).retry_failed(db, containers)
        await db.commit()
    return count


async def test_a_library_ima_refuses_to_list_is_set_aside_while_the_others_keep_syncing(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = two_libraries(), ImaSyncState()
    fake.fail_on[("list_knowledge_page", "kb2")] = ImaAuthError("no access")

    outcome = await run_pass(fake, tmp_path, state, TWO_LIBRARIES)

    assert outcome.finished and not state.needs_reauth and state.failed_containers == ["kb2"]
    assert fake.calls.count("verify") == 1
    assert await statuses(ima_db) == {"one.md": "synced", "two.md": "synced"}


async def test_the_same_refusal_from_a_revoked_key_asks_for_a_reconnect(tmp_path: Path) -> None:
    fake, state = two_libraries(), ImaSyncState()
    fake.fail_on[("list_knowledge_page", "kb2")] = ImaAuthError("no access")
    fake.fail["verify"] = ImaAuthError("revoked")

    outcome = await run_pass(fake, tmp_path, state, TWO_LIBRARIES)

    assert outcome.error_kind == "auth" and state.needs_reauth and state.failed_containers == []


async def test_a_failing_key_check_during_listing_retries_the_slice_and_keeps_the_library_queued(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = two_libraries(), ImaSyncState()
    fake.fail_on[("list_knowledge_page", "kb2")] = ImaAuthError("no access")
    fake.fail["verify"] = ImaTransientError("ima server error (HTTP 503)")

    outcome = await run_pass(fake, tmp_path, state, TWO_LIBRARIES)

    assert outcome.error_kind == "transient" and outcome.retry_after_s is not None and not state.needs_reauth
    assert state.failed_containers == [] and [task.kb_id for task in state.queue] == ["kb2"]

    fake.fail.clear()
    fake.fail_on.clear()
    assert (await run_pass(fake, tmp_path, state, TWO_LIBRARIES)).finished
    assert set((await statuses(ima_db)).values()) == {"synced"}


async def test_a_library_listing_denied_by_a_permission_code_is_set_aside_without_a_key_check(tmp_path: Path) -> None:
    fake, state = two_libraries(), ImaSyncState()
    fake.fail_on[("list_knowledge_page", "kb2")] = envelope_error(100005, "no permission")

    outcome = await run_pass(fake, tmp_path, state, TWO_LIBRARIES)

    assert outcome.finished and state.failed_containers == ["kb2"] and "verify" not in fake.calls


async def test_an_item_ima_refuses_for_permission_is_skipped_as_not_owner(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = two_libraries(), ImaSyncState()
    fake.fail_on[("get_media_info", "m1")] = envelope_error(210011, "no share permission")

    outcome = await run_pass(fake, tmp_path, state, TWO_LIBRARIES)

    by_title = await rows(ima_db)
    assert outcome.finished and "verify" not in fake.calls
    assert (by_title["one.md"].status, by_title["one.md"].error_kind) == (LedgerStatus.UNSUPPORTED, "not_owner")
    assert {title for title, row in by_title.items() if row.status == LedgerStatus.SYNCED} == {"two.md", "three.md", "four.md"}


async def test_a_refused_note_is_skipped_as_not_owner_and_the_other_notes_sync(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake = notes_only()
    fake.fail_on[("get_note_text", "n1")] = envelope_error(210005, "not the note owner")

    outcome = await run_pass(fake, tmp_path, ImaSyncState(), NOTES_ONLY)

    by_title = await rows(ima_db)
    assert outcome.finished
    assert (by_title["Note 1"].status, by_title["Note 1"].error_kind) == (LedgerStatus.UNSUPPORTED, "not_owner")
    assert by_title["Note 0"].status == by_title["Note 2"].status == LedgerStatus.SYNCED


async def test_refused_items_share_one_key_check_and_fail_for_good_without_stopping_the_pool(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = crowded_library(), ImaSyncState()
    denied = {f"m{index}" for index in range(5)}
    for media_id in denied:
        fake.fail_on[("get_media_info", media_id)] = ImaAuthError("no access")

    outcome = await run_pass(fake, tmp_path, state)

    by_title = await rows(ima_db)
    failed = {title: row for title, row in by_title.items() if row.status == LedgerStatus.FAILED}
    assert outcome.finished and not state.needs_reauth and fake.calls.count("verify") == 1
    assert set(failed) == {f"{media_id}.md" for media_id in denied}
    assert {(row.error_kind, row.attempts) for row in failed.values()} == {("permission", MAX_ATTEMPTS)}
    assert sum(row.status == LedgerStatus.SYNCED for row in by_title.values()) == 4


async def test_a_retry_after_the_grant_imports_the_refused_items(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = crowded_library(), ImaSyncState()
    for index in range(5):
        fake.fail_on[("get_media_info", f"m{index}")] = ImaAuthError("no access")
    await run_pass(fake, tmp_path, state)

    fake.fail_on.clear()
    assert await retry_failed(ima_db, ["kb1"]) == 5
    assert (await run_pass(fake, tmp_path, state)).finished

    assert set((await statuses(ima_db)).values()) == {"synced"}


async def test_a_failing_key_check_leaves_the_refused_item_a_transient_failure_and_no_worker_behind(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail_on[("get_media_info", "m1")] = ImaAuthError("refused")
    fake.fail["verify"] = ImaTransientError("ima server error (HTTP 503)")
    tasks_before = asyncio.all_tasks()

    outcome = await run_pass(fake, tmp_path, state)

    guide = (await rows(ima_db))["guide.md"]
    assert outcome.finished and not state.needs_reauth and fake.calls.count("verify") == 1
    assert (guide.status, guide.error_kind) == (LedgerStatus.FAILED, "transient")
    assert (await statuses(ima_db))["deep.md"] == "synced"
    assert [task for task in asyncio.all_tasks() - tasks_before if not task.done()] == []


async def test_a_rate_limit_during_the_key_check_pauses_the_slice_and_keeps_the_item_unfailed(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = library(), ImaSyncState()
    fake.fail_on[("get_media_info", "m1")] = ImaAuthError("refused")
    fake.fail["verify"] = ImaRateLimitError("slow down", retry_after_s=60.0)

    outcome = await run_pass(fake, tmp_path, state)

    assert (outcome.error_kind, outcome.retry_after_s) == ("rate_limit", 60.0)
    assert LedgerStatus.FAILED not in {row.status for row in (await rows(ima_db)).values()}


@pytest.mark.parametrize("failing", ["list_notes_page", "get_note_text"])
async def test_a_notes_rejection_under_a_revoked_key_asks_for_a_reconnect(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], failing: str
) -> None:
    fake, state = notes_only(), ImaSyncState()
    fake.fail[failing] = ImaAuthError("rejected")
    fake.fail["verify"] = ImaAuthError("revoked")

    outcome = await run_pass(fake, tmp_path, state, NOTES_ONLY)

    assert outcome.error_kind == "auth" and state.needs_reauth
    assert LedgerStatus.FAILED not in {row.status for row in (await rows(ima_db)).values()}


async def test_the_gateways_other_frequency_codes_pause_the_slice_instead_of_failing_items(
    tmp_path: Path, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    fake, state = two_libraries(), ImaSyncState()
    fake.fail_on[("get_media_info", "m3")] = envelope_error(200001)

    paused = await run_pass(fake, tmp_path, state, TWO_LIBRARIES)

    assert paused.error_kind == "rate_limit" and paused.retry_after_s is not None and paused.retry_after_s >= 30
    assert LedgerStatus.FAILED not in {row.status for row in (await rows(ima_db)).values()}

    fake.fail_on.clear()
    assert (await run_pass(fake, tmp_path, state, TWO_LIBRARIES)).finished
    assert set((await statuses(ima_db)).values()) == {"synced"}


async def test_a_rate_limit_pause_is_logged_with_ima_s_code(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    fake = two_libraries()
    fake.fail["list_knowledge_page"] = envelope_error(200001)

    with caplog.at_level(logging.WARNING):
        await run_slice(make_ctx(fake, tmp_path, config=TWO_LIBRARIES, state=ImaSyncState()))

    assert any("paused" in message and "code 200001" in message for message in caplog.messages)


async def test_item_failures_are_summarised_once_per_slice_without_titles(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeIma(
        pages={("kb1", ""): page(*(entry(f"m{index}", f"secret-plan-{index}.md") for index in range(3)))},
        media={f"m{index}": file_info(7, url(f"m{index}")) for index in range(3)},
    )
    for index in range(3):
        fake.fail_on[("get_media_info", f"m{index}")] = envelope_error(123456, "quota exceeded")

    with caplog.at_level(logging.WARNING):
        await run_pass(fake, tmp_path, ImaSyncState())

    summaries = [message for message in caplog.messages if "unimported" in message]
    assert len(summaries) == 1
    assert "3 item(s)" in summaries[0] and "permanent=3" in summaries[0] and "code 123456" in summaries[0]
    assert "secret-plan" not in caplog.text


async def test_a_clean_slice_logs_no_failure_summary(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        await run_pass(library(), tmp_path, ImaSyncState())

    assert not any("unimported" in message for message in caplog.messages)


async def test_a_failure_with_no_known_cause_is_summarised_without_a_cause_label(
    tmp_path: Path, downloads: Downloads, caplog: pytest.LogCaptureFixture
) -> None:
    downloads.errors[url("m1")] = TimeoutError()

    with caplog.at_level(logging.WARNING):
        await run_pass(library(), tmp_path, ImaSyncState())

    summaries = [message for message in caplog.messages if "unimported" in message]
    assert len(summaries) == 1 and "timeout=1" in summaries[0] and "cause" not in summaries[0]
