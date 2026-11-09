"""FetchEngine fetch, degradation, and tier-breaker feedback helpers.

[POS]
Mixin: L1/L2/L3 fetch+pipeline, tier degradation, tier-breaker and failure-history feedback.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.documents import Document

from myrm_agent_harness.utils.content_sniff import PayloadKind

from ..fetchers.protocols import Fetcher, FetcherType, FetchResult
from ..processing.antibot_detector import is_blocked as detect_antibot
from ..router import domain_key
from .types import DEGRADABLE_4XX

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine

    from ..processing.pipeline import ContentPipeline

logger = logging.getLogger(__name__)

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except (ImportError, TypeError):
    _PSUTIL_AVAILABLE = False
    logger.warning("psutil not available, resource tracking disabled")


async def _process_and_warn_if_truncated(
    pipeline: ContentPipeline, fetch_result: FetchResult, url: str, max_chars: int
) -> Document | None:
    """Run the content pipeline and warn the user when the content was truncated to fit the context."""
    doc = await pipeline.aprocess(fetch_result, max_chars=max_chars)
    if doc and doc.metadata.get("was_truncated"):
        try:
            from myrm_agent_harness.utils.event_utils import dispatch_custom_event

            await dispatch_custom_event(
                "agent_status",
                {
                    "step_key": "ux_warning_truncated",
                    "status": "warning",
                    "items": [
                        {
                            "text": f"Warning: Content from {url} was intelligently truncated to fit within context limits."
                        }
                    ],
                    "metadata": {"type": "html_truncation", "url": url},
                },
            )
        except Exception as e:
            logger.warning(f"Failed to dispatch truncation event: {e}")
    return doc


class FetchEngineFetchMixin:
    async def _try_fetch_and_process(
        self: FetchEngine,
        url: str,
        fetcher_type: FetcherType,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        max_chars: int = 0,
    ) -> tuple[Document | None, bool, float, float | None, float | None, FetchResult | None]:
        """Fetch with a specified fetcher and process through the pipeline."""
        fetcher_map: dict[FetcherType, Fetcher] = {
            FetcherType.HTTP: self._http_fetcher,
            FetcherType.BROWSER: self._browser_fetcher,
            FetcherType.STEALTH: self._stealth_fetcher,
        }
        fetcher = fetcher_map[fetcher_type]

        if fetcher_type == FetcherType.BROWSER:
            from ..escalation.context import get_bound_browser_launch_mode

            launch_mode = get_bound_browser_launch_mode()
            if launch_mode is None:
                launch_mode = self._browser_launch_mode
            self._browser_fetcher.set_launch_mode_preference(launch_mode)

        if _PSUTIL_AVAILABLE:
            process = psutil.Process()
            cpu_times_start = process.cpu_times()
            mem_start_mb = process.memory_info().rss / 1024 / 1024
        else:
            cpu_times_start = None
            mem_start_mb = None

        start_time = time.time()
        if fetcher_type == FetcherType.HTTP and (etag or last_modified):
            fetch_result: FetchResult | None = await self._http_fetcher.fetch(
                url, etag=etag, last_modified=last_modified
            )
        else:
            fetch_result = await fetcher.fetch(url)
        elapsed = time.time() - start_time
        latency_ms = elapsed * 1000.0

        if _PSUTIL_AVAILABLE and cpu_times_start is not None and mem_start_mb is not None:
            cpu_times_end = process.cpu_times()
            cpu_used = (cpu_times_end.user - cpu_times_start.user) + (cpu_times_end.system - cpu_times_start.system)
            cpu_percent = (cpu_used / elapsed * 100.0) if elapsed > 0 else 0.0
            mem_delta_mb = (process.memory_info().rss / 1024 / 1024) - mem_start_mb
            cpu_percent = max(0.0, cpu_percent)
            memory_mb = max(0.0, mem_delta_mb)
        else:
            cpu_percent = None
            memory_mb = None

        if fetch_result is None:
            return None, True, latency_ms, cpu_percent, memory_mb, None

        if fetch_result.status_code == 304:
            logger.info(f"HTTP 304 Not Modified: {url}")
            return None, False, latency_ms, cpu_percent, memory_mb, fetch_result

        if (
            fetcher_type == FetcherType.HTTP
            and 400 <= fetch_result.status_code < 500
            and fetch_result.status_code not in DEGRADABLE_4XX
        ):
            logger.warning(f"HTTP {fetch_result.status_code} not degradable, abort: {url}")
            return None, False, latency_ms, cpu_percent, memory_mb, None

        # Files (PDF, Office, images) reach here as raw bytes with empty html, so they are routed to a file parser
        # before the empty-shell check. A file no parser reads is just as unreadable in a browser, so it ends the
        # fetch; an error status instead means the server refused the request, which a browser may get past.
        if fetch_result.raw_body is not None:
            from ..processing.binary_router import route_binary_content

            doc = await route_binary_content(fetch_result.raw_body, fetch_result.headers, url)
            if doc is not None or fetch_result.status_code < 400:
                return doc, False, latency_ms, cpu_percent, memory_mb, fetch_result

        # Text (plain, markdown, csv, feeds, source files) is already the content; the HTML-only checks below
        # (empty shell, anti-bot) would reject it for lacking markup.
        if fetch_result.kind is PayloadKind.TEXT and fetch_result.status_code < 400:
            doc = await _process_and_warn_if_truncated(self._pipeline, fetch_result, url, max_chars)
            return doc, True, latency_ms, cpu_percent, memory_mb, fetch_result

        if fetcher_type == FetcherType.HTTP and not fetch_result.has_content:
            logger.warning(f"L1 HTTP returned empty shell, will degrade: {url}")
            return None, True, latency_ms, cpu_percent, memory_mb, None

        from ..extractors.weixin_extractor import (
            has_weixin_js_content,
            is_weixin_article_url,
            parse_weixin_article_html,
        )

        if is_weixin_article_url(url):
            weixin_doc = parse_weixin_article_html(fetch_result.html, url=url)
            if weixin_doc is not None:
                return (
                    weixin_doc,
                    False,
                    latency_ms,
                    cpu_percent,
                    memory_mb,
                    fetch_result,
                )
            if not has_weixin_js_content(fetch_result.html):
                logger.warning(
                    "Weixin URL missing js_content, skipping generic HTML extraction: %s",
                    url,
                )
                return None, True, latency_ms, cpu_percent, memory_mb, fetch_result

        blocked, reason = detect_antibot(fetch_result.status_code, fetch_result.html)
        if blocked:
            logger.warning(f"Anti-bot detected ({reason}): {url}")
            return None, True, latency_ms, cpu_percent, memory_mb, None

        doc = await _process_and_warn_if_truncated(self._pipeline, fetch_result, url, max_chars)
        return doc, True, latency_ms, cpu_percent, memory_mb, fetch_result

    async def _try_and_report(
        self: FetchEngine,
        url: str,
        fetcher_type: FetcherType,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        max_chars: int = 0,
    ) -> tuple[Document | None, bool, float, float | None, float | None, FetchResult | None]:
        """Attempt fetch and report the outcome to the tier breaker."""
        doc, degradable, latency, cpu, mem, fetch_result = await self._try_fetch_and_process(
            url,
            fetcher_type,
            etag=etag,
            last_modified=last_modified,
            max_chars=max_chars,
        )
        # A miss that is final (404, 304, a file no parser reads) says nothing about whether this tier can fetch the
        # site, so it must not count against the tier.
        if doc is not None or degradable:
            self._report_feedback(url, fetcher_type, success=(doc is not None))
        return doc, degradable, latency, cpu, mem, fetch_result

    async def _crawl_with_degradation(
        self: FetchEngine,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        max_chars: int = 0,
        allow_escalation: bool = True,
    ) -> tuple[Document | None, FetchResult | None]:
        """Smart degradation: start on the tier the breaker selects for the domain, degrade tier by tier."""
        start_type = self._tier_breaker.select(domain_key(url))

        if start_type == FetcherType.STEALTH:
            doc, _, _, _, _, result = await self._try_and_report(url, FetcherType.STEALTH, max_chars=max_chars)
            if doc:
                return doc, result

            logger.warning(f"Stealth failed, trying browser: {url}")
            doc, _, _, _, _, result = await self._try_and_report(url, FetcherType.BROWSER, max_chars=max_chars)
            if doc:
                return doc, result
            if allow_escalation:
                esc_doc, esc_result = await self._try_escalation(url, max_chars=max_chars)
                if esc_doc:
                    return esc_doc, esc_result
            return doc, result

        if start_type == FetcherType.BROWSER:
            doc, _, _, _, _, result = await self._try_and_report(url, FetcherType.BROWSER, max_chars=max_chars)
            if doc:
                return doc, result

            logger.warning(f"Browser failed, trying stealth: {url}")
            doc, _, _, _, _, result = await self._try_and_report(url, FetcherType.STEALTH, max_chars=max_chars)
            if doc:
                return doc, result
            if allow_escalation:
                esc_doc, esc_result = await self._try_escalation(url, max_chars=max_chars)
                if esc_doc:
                    return esc_doc, esc_result
            return doc, result

        doc, degradable, _, _, _, result = await self._try_and_report(
            url,
            FetcherType.HTTP,
            etag=etag,
            last_modified=last_modified,
            max_chars=max_chars,
        )
        if doc:
            return doc, result
        if not degradable:
            # A browser cannot read a file the parsers could not, but a remote provider can still try.
            if allow_escalation and result is not None and result.kind is PayloadKind.BINARY:
                esc_doc, esc_result = await self._try_escalation(url, max_chars=max_chars)
                if esc_doc:
                    return esc_doc, esc_result
            return doc, result

        logger.warning(f"HTTP insufficient, degrading to browser: {url}")
        doc, _, _, _, _, result = await self._try_and_report(url, FetcherType.BROWSER, max_chars=max_chars)
        if doc:
            return doc, result

        logger.warning(f"Browser failed, degrading to stealth: {url}")
        doc, _, _, _, _, result = await self._try_and_report(url, FetcherType.STEALTH, max_chars=max_chars)
        if doc:
            return doc, result

        if allow_escalation:
            esc_doc, esc_result = await self._try_escalation(url, max_chars=max_chars)
            if esc_doc:
                return esc_doc, esc_result

        return doc, result

    def _report_feedback(self: FetchEngine, url: str, fetcher_type: FetcherType, *, success: bool) -> None:
        """Report a tier's outcome to the breaker; a failure also feeds the site-experience staleness hint."""
        domain = domain_key(url)
        self._tier_breaker.report(domain, fetcher_type, success=success)
        if not success:
            self._domain_metrics.record_failure(domain, fetcher_type)
