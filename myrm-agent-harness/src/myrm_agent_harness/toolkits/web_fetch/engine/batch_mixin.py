"""FetchEngine batch crawling and cache warm-up helpers.

[INPUT]
- web_fetch.engine.types::FailedResult, SuccessResult (POS: Batch result aliases)

[OUTPUT]
- FetchEngineBatchMixin: ``crawl_many``, ``prefetch_with_retry`` and ``prefetch`` built on ``FetchEngine.crawl``

[POS]
Mixin: concurrent crawling of many URLs under one concurrency cap, retrying warm-up, background prefetch.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .types import FailedResult, SuccessResult

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine

logger = logging.getLogger(__name__)


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
        """Batch-crawl multiple URLs in parallel with global concurrency cap."""
        self._ensure_workers_started()

        success_results: SuccessResult = []
        failed_results: FailedResult = []
        sem = asyncio.Semaphore(max_concurrency)

        async def process(url: str) -> None:
            async with sem:
                doc = await self.crawl(
                    url,
                    force_refresh=force_refresh,
                    max_chars=max_chars,
                    allow_escalation=allow_escalation,
                )
            if doc is not None:
                success_results.append((url, doc))
            else:
                failed_results.append((url, None))

        await asyncio.gather(*(process(u) for u in urls))
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
