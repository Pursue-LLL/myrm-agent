"""Background worker for the memory extraction retry queue.

[INPUT]
app.services.memory.extract_retry.extract_retry_queue (POS: 业务层持久化重试队列)
app.services.memory.extract_retry.retry_chat_memory_extract::run_retry_extract_for_chat (POS: 压缩轨提取执行)
myrm_agent_harness.toolkits.memory::MemoryOperationKind/Status (POS: 账本状态枚举)
app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆账本)

[OUTPUT]
extract_retry_worker: 单进程后台 worker，启动即扫描（重启恢复）+ 每 60s 扫描一次。

[POS]
Lifespan-managed worker. Sweeps the persistent queue on startup (recovers tasks
surviving a restart) and then every interval. Claims due chats, runs compressed-track
extraction under a timeout, applies bounded exponential backoff, and records a terminal
ERROR ledger event when retries are exhausted.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60
RUN_TIMEOUT_SECONDS = 240


class ExtractRetryWorker:
    """Idempotent single-process sweep loop over the extraction retry queue."""

    def __init__(self) -> None:
        self._running: set[str] = set()
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the sweep loop (idempotent)."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="memory-extract-retry")
        logger.info("Memory extract retry worker started")

    async def stop(self) -> None:
        """Cancel the sweep loop and wait for it to finish."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Memory extract retry worker stopped")

    def wake(self) -> None:
        """Trigger an immediate sweep (e.g., right after a retry enqueue)."""
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            # Clear before sweeping so a wake() arriving during the sweep is not
            # consumed by the clear and instead triggers an immediate re-sweep.
            self._wake.clear()
            try:
                async with self._lock:
                    await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Memory extract retry sweep failed: %s", exc)
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=SWEEP_INTERVAL_SECONDS
                )
            except TimeoutError:
                pass

    async def _sweep(self) -> None:
        from app.services.memory.extract_retry import extract_retry_queue as queue
        from app.services.memory.extract_retry.retry_chat_memory_extract import (
            run_retry_extract_for_chat,
        )

        now = datetime.now(UTC)
        try:
            claimed = await queue.claim_due(now, excluding=frozenset(self._running))
        except Exception as exc:
            logger.warning("Memory extract retry claim failed: %s", exc)
            return

        for chat_id, attempt in claimed:
            self._running.add(chat_id)
            try:
                try:
                    async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
                        await run_retry_extract_for_chat(
                            chat_id, source="worker_retry_extract"
                        )
                except Exception as exc:
                    exhausted = await queue.mark_failure(
                        chat_id, attempt, f"{type(exc).__name__}: {exc}"
                    )
                    if exhausted:
                        await _record_terminal_failure(chat_id, attempt, exc)
                    continue
                await queue.delete(chat_id)
            except Exception as exc:
                logger.warning(
                    "Memory extract retry cleanup failed for chat %s: %s",
                    chat_id,
                    exc,
                )
            finally:
                self._running.discard(chat_id)


async def _record_terminal_failure(
    chat_id: str, attempt: int, error: Exception
) -> None:
    """Surface a permanently failed retry in the memory operation ledger."""
    try:
        from myrm_agent_harness.toolkits.memory import (
            MemoryOperationKind,
            MemoryOperationStatus,
        )

        from app.database.connection import get_session
        from app.services.memory.ledger.operation_ledger import (
            MemoryOperationLedgerService,
        )

        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.EXTRACT,
                status=MemoryOperationStatus.ERROR,
                summary="Memory extraction permanently failed after retries",
                source="memory_extract_retry_worker",
                target_kind="chat",
                target_id=chat_id,
                metadata={
                    "chat_id": chat_id,
                    "attempts": attempt,
                    "error": f"{type(error).__name__}: {error}"[:240],
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Failed to record terminal memory extract failure: %s", exc)


extract_retry_worker = ExtractRetryWorker()


__all__ = ["extract_retry_worker"]
