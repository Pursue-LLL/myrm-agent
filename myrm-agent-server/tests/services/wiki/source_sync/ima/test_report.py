"""Status aggregation and item buckets: counts and codes only, never raw error text or secrets."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from myrm_agent_harness.toolkits.cron.types import JobStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.ima import report
from app.services.wiki.source_sync.ima.identity import NOTES_LANE
from app.services.wiki.source_sync.ima.ledger import ImaLedger, InventoryItem, LedgerStatus
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.ima.state import ImaKbSelection, ImaSyncConfig, ImaSyncState, save_ima_config, save_ima_state

NEXT_RUN = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def connected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def credentials() -> ImaCredentials:
        return ImaCredentials(client_id="abcdefghijkl", api_key="never-shown")

    monkeypatch.setattr(report, "load_credentials", credentials)


def item(key: str, title: str, *, container: str = "kb1", media_type: int | None = 7) -> InventoryItem:
    return InventoryItem(
        item_key=key,
        container_id=container,
        container_name="Lib",
        remote_id=key,
        title=title,
        folder_path="Sub",
        media_type=media_type,
        remote_version="v1",
    )


async def _seed(ima_db: async_sessionmaker[AsyncSession]) -> None:
    ledger = ImaLedger(DEFAULT_AGENT_SCOPE)
    items = [
        item("ok", "ok.md"),
        item("lossy", "lossy.pdf", media_type=1),
        item("bad", "bad.md"),
        item("audio", "a.mp3", media_type=15),
    ]
    items += [item("big", "big.pdf", media_type=1), item("gone", "gone.md")]
    async with ima_db() as db:
        await ledger.upsert_inventory(db, items, generation=1, raw_exists=lambda _path: True)
        await db.commit()
    async with ima_db() as db:
        rows = {row.item_key: row for row in await ledger.list_rows(db)}
    async with ima_db() as db:
        await ledger.record_synced(db, rows["ok"], raw_path="ima/ok.md", fidelity="full", notes=[], char_count=100)
        await ledger.record_synced(
            db, rows["lossy"], raw_path="ima/lossy.md", fidelity="partial", notes=["layout_flattened"], char_count=50
        )
        await ledger.record_failure(db, rows["bad"], kind="permanent", final=True)
        await ledger.record_terminal(db, rows["audio"], LedgerStatus.UNSUPPORTED, reason="unsupported_type")
        await ledger.record_terminal(db, rows["big"], LedgerStatus.TOO_LARGE, reason="too_large")
        await db.commit()
    # A second pass that no longer lists "gone".
    async with ima_db() as db:
        await ledger.upsert_inventory(
            db, [entry for entry in items if entry.item_key != "gone"], generation=2, raw_exists=lambda _path: True
        )
        await ledger.mark_remote_deleted(db, generation=2, container_ids=["kb1"])
        await db.commit()


async def test_status_of_a_fresh_install_is_disconnected_and_empty(
    ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nobody() -> None:
        return None

    async def no_job(agent_id: str | None) -> None:
        return None

    monkeypatch.setattr(report, "load_credentials", nobody)
    monkeypatch.setattr(report, "find_job", no_job)

    status = await report.build_status(None)

    assert status.connected is False and status.account_hint == "" and status.job.state == "none"
    assert status.counts.total == 0 and status.knowledge_bases == [] and status.include_notes is True


async def test_status_aggregates_counts_job_state_and_masks_the_account(
    ima_db: async_sessionmaker[AsyncSession], connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(ima_db)
    async with ima_db() as db:
        await save_ima_config(
            db, ImaSyncConfig(knowledge_bases=[ImaKbSelection(id="kb1", name="Lib")], include_notes=False), agent_id=None
        )
        await save_ima_state(
            db,
            ImaSyncState(phase="fetch", backfill_complete=False, failed_containers=[NOTES_LANE], last_error_kind="rate_limit"),
            agent_id=None,
        )

    async def paused_job(agent_id: str | None) -> SimpleNamespace:
        return SimpleNamespace(status=JobStatus.PAUSED, next_run_at=NEXT_RUN)

    monkeypatch.setattr(report, "find_job", paused_job)

    status = await report.build_status(None)

    assert status.connected and status.account_hint == "abcd…ijkl"
    assert "never-shown" not in status.model_dump_json()
    assert status.job.state == "paused" and status.job.next_run_at == NEXT_RUN
    assert status.phase == "fetch" and status.notes_unavailable and status.last_error_kind == "rate_limit"
    counts = status.counts
    assert (counts.total, counts.synced, counts.partial) == (6, 2, 1)
    assert (counts.failed, counts.unsupported, counts.too_large, counts.remote_deleted) == (1, 1, 1, 1)
    assert status.total_chars == 150


async def test_active_job_state(
    ima_db: async_sessionmaker[AsyncSession], connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def active_job(agent_id: str | None) -> SimpleNamespace:
        return SimpleNamespace(status=JobStatus.ACTIVE, next_run_at=None)

    monkeypatch.setattr(report, "find_job", active_job)
    assert (await report.build_status(None)).job.state == "active"


async def test_item_buckets_expose_codes_only(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _seed(ima_db)

    attention = await report.list_items(None, "attention")
    assert {(view.title, view.status, view.reason) for view in attention} == {
        ("bad.md", "failed", "permanent"),
        ("a.mp3", "unsupported", "unsupported_type"),
        ("big.pdf", "too_large", "too_large"),
    }
    assert {view.media_kind for view in attention} == {"markdown", "audio", "pdf"}

    lossy = await report.list_items(None, "lossy")
    assert [(view.title, view.notes, view.container_name, view.folder_path) for view in lossy] == [
        ("lossy.pdf", ["layout_flattened"], "Lib", "Sub")
    ]

    gone = await report.list_items(None, "remote_deleted")
    assert [(view.title, view.status) for view in gone] == [("gone.md", "remote_deleted")]
