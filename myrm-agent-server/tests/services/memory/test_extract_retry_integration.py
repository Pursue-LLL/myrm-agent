"""Integration tests: real SQLite-backed retry queue driven through the worker sweep.

Covers the full durable cycle (enqueue -> claim -> extract -> delete/backoff) plus
startup recovery of a task whose owner crashed mid-flight, and the real cooperation
between worker and run_retry_extract_for_chat on no-op turn paths.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import MemoryExtractRetryModel, MemoryOperationEventModel
from app.services.memory.extract_retry import extract_retry_queue as queue
from app.services.memory.extract_retry.extract_retry_worker import ExtractRetryWorker

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.mark.asyncio
async def test_full_success_cycle_deletes_row(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """enqueue -> worker sweep (extract ok) -> queue row removed."""
    assert await queue.enqueue("chat-1", reset_failed=False) == "queued"

    worker = ExtractRetryWorker()
    with patch(
        "app.services.memory.retry_chat_memory_extract.run_retry_extract_for_chat",
        AsyncMock(return_value=True),
    ):
        await worker._sweep()

    assert await fetch_retry_row("chat-1") is None
    assert worker._running == set()


@pytest.mark.asyncio
async def test_failure_backoff_then_retry_recovers(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """Failed attempt schedules exponential backoff; a later due sweep recovers."""
    await queue.enqueue("chat-1", reset_failed=False)

    worker = ExtractRetryWorker()
    with patch(
        "app.services.memory.retry_chat_memory_extract.run_retry_extract_for_chat",
        AsyncMock(side_effect=RuntimeError("llm unavailable")),
    ):
        await worker._sweep()

    row = await fetch_retry_row("chat-1")
    assert row is not None
    assert row.status == "pending"
    assert row.attempt == 1
    assert row.next_attempt_at > datetime.now(UTC).replace(tzinfo=None)
    assert row.last_error == "RuntimeError: llm unavailable"

    async with test_db() as db:
        row = await db.get(MemoryExtractRetryModel, "chat-1")
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    with patch(
        "app.services.memory.retry_chat_memory_extract.run_retry_extract_for_chat",
        AsyncMock(return_value=True),
    ):
        await worker._sweep()

    assert await fetch_retry_row("chat-1") is None


@pytest.mark.asyncio
async def test_restart_reclaims_inflight_task(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """A claimed-but-crashed task stays pending and a fresh worker reclaims it."""
    await queue.enqueue("chat-1", reset_failed=False)

    crashed_worker = ExtractRetryWorker()
    claimed = await queue.claim_due(
        datetime.now(UTC), excluding=frozenset(crashed_worker._running)
    )
    assert [chat_id for chat_id, _ in claimed] == ["chat-1"]
    # Crash: no delete, no mark_failure — the row remains pending with attempt bumped.

    restarted_worker = ExtractRetryWorker()
    with patch(
        "app.services.memory.retry_chat_memory_extract.run_retry_extract_for_chat",
        AsyncMock(return_value=True),
    ):
        await restarted_worker._sweep()

    assert await fetch_retry_row("chat-1") is None


@pytest.mark.asyncio
async def test_real_worker_run_retry_no_op_turn_deletes_row(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """Real cooperation: run_retry_extract_for_chat returns False for a chat whose
    latest turn has no assistant reply, and the worker deletes the queue row.

    Key-path code (queue -> worker -> run_retry_extract_for_chat) runs unmocked.
    """
    await _insert_chat(test_db, "chat-incomplete")
    await _insert_message(test_db, "chat-incomplete", "m1", "user", "hello")
    assert await queue.enqueue("chat-incomplete", reset_failed=False) == "queued"

    worker = ExtractRetryWorker()
    await worker._sweep()

    assert await fetch_retry_row("chat-incomplete") is None
    assert worker._running == set()


@pytest.mark.asyncio
async def test_real_worker_run_retry_missing_chat_deletes_row(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """Real cooperation: run_retry_extract_for_chat returns False when the chat is
    gone (already deleted), and the worker removes the stale queue row."""
    assert await queue.enqueue("chat-deleted", reset_failed=False) == "queued"

    worker = ExtractRetryWorker()
    await worker._sweep()

    assert await fetch_retry_row("chat-deleted") is None


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="E2E requires BASIC_API_KEY and LITE_API_KEY from .env.test",
)
async def test_real_llm_full_retry_cycle(
    test_db,
    monkeypatch: pytest.MonkeyPatch,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """Real end-to-end retry: queue -> worker -> real run_retry_extract_for_chat ->
    real harness extraction (LLM) -> queue row removed.

    No key-path mocking. The WebUI provider settings (normally stored in the DB)
    are seeded into the test database from .env.test, so binding resolution,
    extraction LLM resolution, memory manager construction, and auto_extract_memories
    all run against real providers.
    """
    # Bypass the 30s load_user_configs cache so the seeded providers are picked up.
    monkeypatch.setenv("MYRM_E2E_SHPOIB", "1")
    await _seed_e2e_user_configs(test_db)

    await _insert_chat(test_db, "chat-e2e-retry")
    await _insert_message(
        test_db,
        "chat-e2e-retry",
        "m1",
        "user",
        "I prefer Rust for systems programming because of its memory safety guarantees.",
    )
    await _insert_message(
        test_db,
        "chat-e2e-retry",
        "m2",
        "assistant",
        "Rust's ownership model is what makes its memory safety guarantees possible at compile time.",
    )
    assert await queue.enqueue("chat-e2e-retry", reset_failed=False) == "queued"

    worker = ExtractRetryWorker()
    await worker._sweep()

    row = await fetch_retry_row("chat-e2e-retry")
    if row is not None:
        print(f"\nE2E row survived; attempt={row.attempt} error={row.last_error}")
    assert row is None
    assert worker._running == set()


def _build_e2e_providers() -> dict[str, object]:
    """Build a WebUI-style providers config dict from .env.test.

    Mirrors the structure produced by the model-service settings page so that
    load_user_configs / model_resolver can resolve real LLMs without mocking.
    """
    basic_model = os.environ["BASIC_MODEL"]  # e.g. "openai-like/deepseek-v4-flash"
    lite_model = os.environ["LITE_MODEL"]  # e.g. "minimax/MiniMax-M3"
    return {
        "providers": [
            {
                "id": "e2e-basic",
                "providerType": basic_model.split("/", 1)[0],
                "isEnabled": True,
                "apiUrl": os.environ["BASIC_BASE_URL"],
                "apiKeys": [{"key": os.environ["BASIC_API_KEY"], "isActive": True}],
            },
            {
                "id": "e2e-lite",
                "providerType": lite_model.split("/", 1)[0],
                "isEnabled": True,
                "apiUrl": os.environ["LITE_BASE_URL"],
                "apiKeys": [{"key": os.environ["LITE_API_KEY"], "isActive": True}],
            },
        ],
        "defaultModelConfig": {
            "baseModel": {
                "primary": {
                    "providerId": "e2e-basic",
                    "model": basic_model.split("/", 1)[1],
                },
            },
            "liteModel": {
                "primary": {
                    "providerId": "e2e-lite",
                    "model": lite_model.split("/", 1)[1],
                },
            },
        },
    }


async def _seed_e2e_user_configs(factory: SessionFactory) -> None:
    """Seed WebUI-style providers + retrieval settings into the test DB from .env.test."""
    from app.database.models import UserConfig

    retrieval = {
        "embeddingApplied": True,
        "embeddingConfig": {
            "provider": "siliconflow",
            "model": os.environ["EMBEDDING_MODEL"],
            "apiKey": os.environ["EMBEDDING_API_KEY"],
            "apiBase": os.environ["EMBEDDING_BASE_URL"],
        },
    }
    async with factory() as db:
        db.add(
            UserConfig(
                id="e2e-providers",
                config_key="providers",
                config_value=_build_e2e_providers(),
                version="0",
                last_device_id="e2e-test",
            )
        )
        db.add(
            UserConfig(
                id="e2e-retrieval",
                config_key="retrieval",
                config_value=retrieval,
                version="0",
                last_device_id="e2e-test",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_real_worker_lifecycle_enqueue_wake_processes_row(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """Real worker loop lifecycle: start -> enqueue -> wake -> sweep -> row deleted -> stop.

    Exercises the production startup path (background loop, not a direct _sweep call)
    against a real no-op turn, so run_retry_extract_for_chat returns False and the
    worker cleans up the row. This is the exact path manual retries take at runtime.
    """
    await _insert_chat(test_db, "chat-live")
    await _insert_message(test_db, "chat-live", "m1", "user", "hello")

    worker = ExtractRetryWorker()
    await worker.start()
    try:
        assert await queue.enqueue("chat-live", reset_failed=False) == "queued"
        worker.wake()
        await _wait_for_row_gone(fetch_retry_row, "chat-live")
    finally:
        await worker.stop()

    assert worker._task is None
    assert worker._running == set()


@pytest.mark.asyncio
async def test_attempts_exhausted_marks_failed_and_records_ledger(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """MAX_ATTEMPTS failures flip the row to failed, stop reclaims, and record a
    terminal ERROR event in the operation ledger (the user-visible failure signal)."""
    assert await queue.enqueue("chat-exhaust", reset_failed=False) == "queued"

    worker = ExtractRetryWorker()
    with patch(
        "app.services.memory.retry_chat_memory_extract.run_retry_extract_for_chat",
        AsyncMock(side_effect=RuntimeError("provider down")),
    ):
        for _ in range(queue.MAX_ATTEMPTS):
            # Force the backoff window to be due so the next sweep reclaims it.
            async with test_db() as db:
                row = await db.get(MemoryExtractRetryModel, "chat-exhaust")
                assert row is not None
                row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            await worker._sweep()

    row = await fetch_retry_row("chat-exhaust")
    assert row is not None
    assert row.status == "failed"
    assert row.attempt == queue.MAX_ATTEMPTS
    assert row.last_error == "RuntimeError: provider down"

    # Failed rows are never reclaimed.
    claimed = await queue.claim_due(
        datetime.now(UTC) + timedelta(days=1), excluding=frozenset()
    )
    assert claimed == []

    # A terminal ERROR event was recorded in the operation ledger.
    async with test_db() as db:
        events = (
            await db.execute(
                select(MemoryOperationEventModel).where(
                    MemoryOperationEventModel.target_id == "chat-exhaust",
                    MemoryOperationEventModel.kind == "extract",
                    MemoryOperationEventModel.status == "error",
                )
            )
        ).scalars().all()
    assert len(events) == 1
    assert events[0].source == "memory_extract_retry_worker"


async def _wait_for_row_gone(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
    chat_id: str,
    timeout: float = 5.0,
) -> None:
    """Poll until the retry queue row disappears (bounded wait)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await fetch_retry_row(chat_id) is None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"retry row {chat_id} was not cleaned up within {timeout}s")


async def _insert_chat(factory: SessionFactory, chat_id: str) -> None:
    from app.database.models.chat import Chat

    now = datetime.now(UTC)
    async with factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title=f"retry-it-{chat_id}",
                is_incognito=False,
                created_at=now,
                updated_at=now,
            )
        )
        await db.commit()


async def _insert_message(
    factory: SessionFactory, chat_id: str, message_id: str, role: str, content: str
) -> None:
    from app.database.models.chat import Message

    async with factory() as db:
        db.add(
            Message(
                id=message_id,
                chat_id=chat_id,
                role=role,
                content=content,
                sent_at=datetime.now(UTC),
                sent_timezone="UTC",
                is_active=True,
            )
        )
        await db.commit()
