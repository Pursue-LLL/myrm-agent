"""FetchEngine batch crawling and cache warm-up helpers.

[INPUT]
- web_fetch.engine.types::FailedResult, SuccessResult (POS: Batch result aliases)

[OUTPUT]
- FetchEngineBatchMixin: ``crawl_many``, ``prefetch_with_retry`` and ``prefetch`` built on ``FetchEngine.crawl``

[POS]
Mixin: concurrent crawling of many URLs under one concurrency cap and a per-URL patience, retrying warm-up,
background prefetch.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING

from .types import FailedResult, SuccessResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from langchain_core.documents import Document

    from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine

logger = logging.getLogger(__name__)

# Once any page is in hand, a URL that has run this long is cancelled instead of holding the whole call.
_STRAGGLER_AFTER_S = 25.0
# A URL past its own crawl timeout is only unwinding (closing its browser page): the call stops waiting this long after.
_UNWIND_GRACE_S = 5.0
# A cancelled URL gets this long to release its browser page before it is left to finish on its own.
_CANCEL_SETTLE_S = 2.0


def _consume_outcome(task: asyncio.Task[Document | None]) -> None:
    """Mark the outcome of a fetch nobody awaits any more as seen; the engine has already logged its errors."""
    if not task.cancelled():
        task.exception()


async def _abandon(fetches: Mapping[asyncio.Task[Document | None], tuple[str, float]], *, crawl_timeout: float) -> None:
    """Stop waiting for ``fetches`` ({task: (url, start time)}).

    A fetch still inside its crawl timeout is cancelled and given ``_CANCEL_SETTLE_S`` to release its browser page.
    One past it is already unwinding from that timeout's own cancel; a second cancel would cut its page cleanup
    short, so it is left to finish on its own.
    """
    now = asyncio.get_running_loop().time()
    cancelled: list[asyncio.Task[Document | None]] = []
    for task, (_, started_at) in fetches.items():
        task.add_done_callback(_consume_outcome)
        if now - started_at < crawl_timeout:
            task.cancel()
            cancelled.append(task)
    if cancelled:
        await asyncio.wait(cancelled, timeout=_CANCEL_SETTLE_S)


class FetchEngineBatchMixin:
    async def crawl_many(
        self: FetchEngine,
        urls: list[str],
        *,
        max_concurrency: int = 10,
        force_refresh: bool = False,
        max_chars: int = 0,
        allow_escalation: bool = True,
    ) -> tuple[SuccessResult, FailedResult]:
        """Batch-crawl URLs in parallel under one concurrency cap; one slow URL cannot hold the call hostage.

        Each URL is judged by how long its own fetch has run. With no page in hand yet it is awaited until its crawl
        timeout plus ``_UNWIND_GRACE_S``; once any page is in hand it gets ``_STRAGGLER_AFTER_S`` and is then
        cancelled. A URL given up on is reported as failed, so a call holding a page never ends up empty-handed.
        """
        self._ensure_workers_started()
        loop = asyncio.get_running_loop()
        hard_s = self._crawl_timeout + _UNWIND_GRACE_S
        soft_s = min(_STRAGGLER_AFTER_S, hard_s)
        success_results: SuccessResult = []
        failed_results: FailedResult = []
        queued = deque(urls)
        running: dict[asyncio.Task[Document | None], tuple[str, float]] = {}  # task -> (url, start time)

        try:
            while queued or running:
                while queued and len(running) < max_concurrency:
                    url = queued.popleft()
                    fetch = self.crawl(
                        url,
                        force_refresh=force_refresh,
                        max_chars=max_chars,
                        allow_escalation=allow_escalation,
                    )
                    running[asyncio.create_task(fetch)] = (url, loop.time())

                patience_s = soft_s if success_results else hard_s
                # A fetch that finished while an earlier give-up was settling is collected below, not given up on.
                overdue = {
                    task: run for task, run in running.items() if not task.done() and loop.time() - run[1] >= patience_s
                }
                if overdue:
                    for task in overdue:
                        del running[task]
                    skipped = [url for url, _ in overdue.values()]
                    logger.warning(
                        "Batch crawl gave up on %d slow URL(s) after %.0fs: %s", len(skipped), patience_s, skipped
                    )
                    failed_results.extend((url, None) for url in skipped)
                    await _abandon(overdue, crawl_timeout=self._crawl_timeout)
                    continue

                next_deadline = min(started_at for _, started_at in running.values()) + patience_s
                done, _ = await asyncio.wait(
                    running, timeout=next_deadline - loop.time(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in [t for t in running if t in done]:
                    url, _ = running.pop(task)
                    doc = task.result()
                    if doc is not None:
                        success_results.append((url, doc))
                    else:
                        failed_results.append((url, None))
        except (Exception, asyncio.CancelledError):  # not BaseException: a coroutine closed at teardown must not await
            await _abandon(running, crawl_timeout=self._crawl_timeout)
            raise
        return success_results, failed_results

    async def prefetch_with_retry(
        self: FetchEngine,
        urls: list[str],
        *,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_concurrency: int = 10,
    ) -> tuple[SuccessResult, FailedResult]:
        """Warm up cache (concurrent + auto-retry on failure + exponential backoff)."""
        self._ensure_workers_started()

        success_results: SuccessResult = []
        failed_results: FailedResult = []
        results_lock = asyncio.Lock()
        sem = asyncio.Semaphore(max_concurrency)

        async def retry_one(url: str) -> None:
            async with sem:
                retry_count = 0
                backoff = initial_backoff
                last_error = None

                while retry_count <= max_retries:
                    try:
                        force_refresh = retry_count > 0
                        doc = await self.crawl(url, force_refresh=force_refresh)
                        if doc is not None:
                            async with results_lock:
                                success_results.append((url, doc))
                            return
                        last_error = "Crawl returned None"
                        logger.warning(
                            f"Prefetch failed (attempt {retry_count + 1}/{max_retries + 1}): {url} — {last_error}"
                        )
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"Prefetch failed (attempt {retry_count + 1}/{max_retries + 1}): {url} — {e}")

                    retry_count += 1
                    if retry_count <= max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2

                logger.error(f"Prefetch exhausted all retries: {url} — {last_error}")
                async with results_lock:
                    failed_results.append((url, None))

        await asyncio.gather(*(retry_one(u) for u in urls))
        return success_results, failed_results

    async def prefetch(self: FetchEngine, urls: list[str], *, max_concurrency: int = 5) -> None:
        """Cache warmup: background async load URLs into cache."""
        self._ensure_workers_started()

        sem = asyncio.Semaphore(max_concurrency)

        async def prefetch_one(url: str) -> None:
            async with sem:
                try:
                    await self.crawl(url)
                except Exception:
                    logger.warning(f"Prefetch failed: {url}")

        await asyncio.gather(*(prefetch_one(u) for u in urls), return_exceptions=True)
