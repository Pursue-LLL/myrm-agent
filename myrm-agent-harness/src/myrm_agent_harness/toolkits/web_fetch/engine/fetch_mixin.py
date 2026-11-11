"""FetchEngine network fetch, platform fast-path, degradation, and tier-breaker feedback helpers.

[POS]
Mixin: platform fast-paths (YouTube, Bilibili, WeChat, X) ahead of the L1/L2/L3 tier ladder, L1/L2/L3
fetch+pipeline, tier degradation, tier-breaker and failure-history feedback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_core.documents import Document

from myrm_agent_harness.utils.content_sniff import PayloadKind

from ..extractors.bilibili_extractor import extract_bilibili_subtitle, is_bilibili_url
from ..extractors.weixin_extractor import extract_weixin_article, is_weixin_article_url
from ..extractors.x_extractor import extract_x_post, is_x_url
from ..extractors.youtube_extractor import extract_youtube_transcript, is_youtube_url
from ..fetchers.protocols import Fetcher, FetcherType, FetchResult
from ..processing.antibot_detector import is_blocked as detect_antibot
from ..router import domain_key
from .types import DEGRADABLE_4XX

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine

    from ..processing.pipeline import ContentPipeline

logger = logging.getLogger(__name__)


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
    ) -> tuple[Document | None, bool, FetchResult | None]:
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

        if fetcher_type == FetcherType.HTTP and (etag or last_modified):
            fetch_result: FetchResult | None = await self._http_fetcher.fetch(
                url, etag=etag, last_modified=last_modified
            )
        else:
            fetch_result = await fetcher.fetch(url)

        if fetch_result is None:
            return None, True, None

        if fetch_result.status_code == 304:
            logger.info(f"HTTP 304 Not Modified: {url}")
            return None, False, fetch_result

        if (
            fetcher_type == FetcherType.HTTP
            and 400 <= fetch_result.status_code < 500
            and fetch_result.status_code not in DEGRADABLE_4XX
        ):
            logger.warning(f"HTTP {fetch_result.status_code} not degradable, abort: {url}")
            return None, False, None

        # Files (PDF, Office, images) reach here as raw bytes with empty html, so they are routed to a file parser
        # before the empty-shell check. A file no parser reads is just as unreadable in a browser, so it ends the
        # fetch; an error status instead means the server refused the request, which a browser may get past.
        if fetch_result.raw_body is not None:
            from ..processing.binary_router import route_binary_content

            doc = await route_binary_content(fetch_result.raw_body, fetch_result.headers, url)
            if doc is not None or fetch_result.status_code < 400:
                return doc, False, fetch_result

        # Text (plain, markdown, csv, feeds, source files) is already the content; the HTML-only checks below
        # (empty shell, anti-bot) would reject it for lacking markup.
        if fetch_result.kind is PayloadKind.TEXT and fetch_result.status_code < 400:
            doc = await _process_and_warn_if_truncated(self._pipeline, fetch_result, url, max_chars)
            return doc, True, fetch_result

        if fetcher_type == FetcherType.HTTP and not fetch_result.has_content:
            logger.warning(f"L1 HTTP returned empty shell, will degrade: {url}")
            return None, True, None

        from ..extractors.weixin_extractor import has_weixin_js_content, parse_weixin_article_html

        if is_weixin_article_url(url):
            weixin_doc = parse_weixin_article_html(fetch_result.html, url=url)
            if weixin_doc is not None:
                return weixin_doc, False, fetch_result
            if not has_weixin_js_content(fetch_result.html):
                logger.warning(
                    "Weixin URL missing js_content, skipping generic HTML extraction: %s",
                    url,
                )
                return None, True, fetch_result

        blocked, reason = detect_antibot(fetch_result.status_code, fetch_result.html)
        if blocked:
            logger.warning(f"Anti-bot detected ({reason}): {url}")
            return None, True, None

        doc = await _process_and_warn_if_truncated(self._pipeline, fetch_result, url, max_chars)
        return doc, True, fetch_result

    async def _try_and_report(
        self: FetchEngine,
        url: str,
        fetcher_type: FetcherType,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        max_chars: int = 0,
    ) -> tuple[Document | None, bool, FetchResult | None]:
        """Attempt fetch and report the outcome to the tier breaker."""
        doc, degradable, fetch_result = await self._try_fetch_and_process(
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
        return doc, degradable, fetch_result

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
            doc, _, result = await self._try_and_report(url, FetcherType.STEALTH, max_chars=max_chars)
            if doc:
                return doc, result

            logger.warning(f"Stealth failed, trying browser: {url}")
            doc, _, result = await self._try_and_report(url, FetcherType.BROWSER, max_chars=max_chars)
            if doc:
                return doc, result
            if allow_escalation:
                esc_doc, esc_result = await self._try_escalation(url, max_chars=max_chars)
                if esc_doc:
                    return esc_doc, esc_result
            return doc, result

        if start_type == FetcherType.BROWSER:
            doc, _, result = await self._try_and_report(url, FetcherType.BROWSER, max_chars=max_chars)
            if doc:
                return doc, result

            logger.warning(f"Browser failed, trying stealth: {url}")
            doc, _, result = await self._try_and_report(url, FetcherType.STEALTH, max_chars=max_chars)
            if doc:
                return doc, result
            if allow_escalation:
                esc_doc, esc_result = await self._try_escalation(url, max_chars=max_chars)
                if esc_doc:
                    return esc_doc, esc_result
            return doc, result

        doc, degradable, result = await self._try_and_report(
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
        doc, _, result = await self._try_and_report(url, FetcherType.BROWSER, max_chars=max_chars)
        if doc:
            return doc, result

        logger.warning(f"Browser failed, degrading to stealth: {url}")
        doc, _, result = await self._try_and_report(url, FetcherType.STEALTH, max_chars=max_chars)
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

    async def _fetch_from_network(
        self: FetchEngine,
        url: str,
        *,
        etag: str | None,
        last_modified: str | None,
        max_chars: int,
        allow_escalation: bool,
    ) -> tuple[Document | None, FetchResult | None]:
        """Fetch ``url`` over the network: the platform fast-path when it has one, then the tier ladder.

        Each stage runs under its own crawl timeout, so a URL whose fast-path misses can take twice the cap.
        """

        async def degrade() -> tuple[Document | None, FetchResult | None]:
            async with asyncio.timeout(self._crawl_timeout):
                return await self._crawl_with_degradation(
                    url,
                    etag=etag,
                    last_modified=last_modified,
                    max_chars=max_chars,
                    allow_escalation=allow_escalation,
                )

        proxy_pool = self._http_fetcher._proxy_pool
        if is_youtube_url(url):
            async with asyncio.timeout(self._crawl_timeout):
                doc = await extract_youtube_transcript(
                    url, preferred_languages=self._youtube_languages, proxy_pool=proxy_pool
                )
            return (doc, None) if doc is not None else await degrade()

        if is_bilibili_url(url):
            async with asyncio.timeout(self._crawl_timeout):
                cookies = await self._load_bilibili_cookies()
                doc = await extract_bilibili_subtitle(url, cookies=cookies, proxy_pool=proxy_pool)
            return (doc, None) if doc is not None else await degrade()

        if is_weixin_article_url(url):
            async with asyncio.timeout(self._crawl_timeout):
                doc = await extract_weixin_article(url, proxy_pool=proxy_pool)
            if doc is not None:
                logger.info("Weixin article fast-path succeeded: %s", url)
                return doc, None
            logger.info("Weixin article fast-path missed, degrading to browser: %s", url)
            doc, fetch_result = await degrade()
            if doc is not None:
                logger.info("Weixin article browser degradation succeeded: %s", url)
            else:
                logger.warning("Weixin article fetch failed after degradation: %s", url)
            return doc, fetch_result

        if is_x_url(url):
            async with asyncio.timeout(self._crawl_timeout):
                doc = await extract_x_post(url, proxy_pool=proxy_pool)
            if doc is not None:
                logger.info("Twitter/X post fast-path succeeded: %s", url)
                return doc, None
            logger.info("Twitter/X post fast-path missed, degrading to standard fetch: %s", url)

        return await degrade()
