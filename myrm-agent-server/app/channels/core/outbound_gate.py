"""Pre-publish outbound content & link liveness gate for message bus.

Extracts external URLs from outbound messages, probes them concurrently via
fast HTTP HEAD (with GET-range fallback on 403/405), caches results with TTL,
and enforces fail-closed HOLD policy on dead links for unattended Cron/broadcast
channels or soft-warning downgrade on interactive chats.

[INPUT]
- channels.types::OutboundMessage
- channels.types.messages::MessagePriority

[OUTPUT]
- OutboundContentGate: asynchronous link liveness and attribution gate
- get_outbound_content_gate(): singleton access
- apply_outbound_content_gate(): convenience filter for MessageBus dispatch loop
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from collections import OrderedDict
from typing import Final
from urllib.parse import urlparse

import httpx

from app.channels.i18n import channel_t, get_locale_from_metadata
from app.channels.types.messages import OutboundMessage

logger = logging.getLogger(__name__)

# Regex matching absolute HTTP/HTTPS URLs (excluding trailing punctuation)
_URL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"https?://[^\s<>\)\]\}\"\']+",
    re.IGNORECASE,
)

# Punctuation to strip from URL tail
_TRAILING_PUNCTUATION: Final[str] = ".,;:!?)'\""

# High-trust major domains that bypass aggressive dead-link probes (fast-path)
_TRUSTED_HOSTS: Final[frozenset[str]] = frozenset({
    "localhost",
    "127.0.0.1",
    "github.com",
    "gitlab.com",
    "google.com",
    "wikipedia.org",
    "python.org",
    "anthropic.com",
    "openai.com",
})

# Custom browser-like User-Agent for HEAD/GET probing
_PROBE_UA: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 MyrmOutboundGate/1.0"
)


@dataclasses.dataclass(frozen=True, slots=True)
class LinkProbeResult:
    """Outcome of probing a single URL."""

    url: str
    is_alive: bool
    status_code: int | None
    error: str | None = None


class OutboundContentGate:
    """Evaluates outbound message content before channel egress."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 1.5,
        cache_ttl_seconds: float = 600.0,
        cache_max_entries: int = 1000,
        enabled: bool = True,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_max_entries = cache_max_entries
        self._enabled = enabled
        self._cache: OrderedDict[str, tuple[float, LinkProbeResult]] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def extract_urls(self, text: str) -> list[str]:
        """Extract all valid HTTP/HTTPS URLs from the given content string."""
        if not text:
            return []
        raw_matches = _URL_REGEX.findall(text)
        urls: list[str] = []
        for raw in raw_matches:
            cleaned = raw.rstrip(_TRAILING_PUNCTUATION)
            if cleaned and cleaned not in urls:
                urls.append(cleaned)
        return urls

    async def probe_url(self, url: str) -> LinkProbeResult:
        """Probe a single URL using cached results or fast async HTTP request."""
        now = time.monotonic()

        async with self._lock:
            if url in self._cache:
                timestamp, cached_result = self._cache[url]
                if now - timestamp < self._cache_ttl_seconds:
                    self._cache.move_to_end(url)
                    return cached_result
                del self._cache[url]

        # Check trusted host fast-path
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
            if any(hostname == th or hostname.endswith("." + th) for th in _TRUSTED_HOSTS):
                res = LinkProbeResult(url=url, is_alive=True, status_code=200)
                await self._store_cache(url, res)
                return res
        except Exception:
            pass

        # Perform network probe
        result = await self._network_probe(url)
        await self._store_cache(url, result)
        return result

    async def _store_cache(self, url: str, result: LinkProbeResult) -> None:
        now = time.monotonic()
        async with self._lock:
            self._cache[url] = (now, result)
            self._cache.move_to_end(url)
            while len(self._cache) > self._cache_max_entries:
                self._cache.popitem(last=False)

    async def _network_probe(self, url: str) -> LinkProbeResult:
        headers = {"User-Agent": _PROBE_UA}
        transport_limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=self._timeout_seconds,
                follow_redirects=True,
                limits=transport_limits,
            ) as client:
                try:
                    # Step 1: Fast HEAD request
                    resp = await client.head(url)
                    # 200-399 is definitely alive
                    if 200 <= resp.status_code < 400:
                        return LinkProbeResult(url=url, is_alive=True, status_code=resp.status_code)
                    # 405 Method Not Allowed or 403 Forbidden: fallback to GET range
                    if resp.status_code in (403, 405):
                        resp_get = await client.get(url, headers={"Range": "bytes=0-0"})
                        if 200 <= resp_get.status_code < 400 or resp_get.status_code == 206:
                            return LinkProbeResult(
                                url=url, is_alive=True, status_code=resp_get.status_code
                            )
                        # If still 403, host exists and answered (bot block rather than dead link)
                        if resp_get.status_code == 403:
                            return LinkProbeResult(
                                url=url, is_alive=True, status_code=403
                            )
                    # 404 / 410 / 5xx considered dead or broken
                    return LinkProbeResult(
                        url=url,
                        is_alive=False,
                        status_code=resp.status_code,
                        error=f"HTTP {resp.status_code}",
                    )
                except httpx.HTTPStatusError as e:
                    return LinkProbeResult(
                        url=url,
                        is_alive=False,
                        status_code=e.response.status_code if e.response else None,
                        error=str(e),
                    )
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.debug("Outbound probe timeout or error for '%s': %s", url, e)
            return LinkProbeResult(
                url=url,
                is_alive=False,
                status_code=None,
                error=type(e).__name__,
            )

    async def check_message(self, msg: OutboundMessage) -> tuple[bool, list[LinkProbeResult]]:
        """Probe all extracted URLs in parallel.

        Returns:
            (all_alive, probe_results)
        """
        if not self._enabled or not msg.content:
            return True, []

        urls = self.extract_urls(msg.content)
        if not urls:
            return True, []

        tasks = [self.probe_url(u) for u in urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        all_alive = all(r.is_alive for r in results)
        return all_alive, list(results)

    async def evaluate_and_apply(self, msg: OutboundMessage) -> OutboundMessage | None:
        """Applies outbound content gate policy to the message.

        - If all links are alive (or no links): returns msg unchanged.
        - If dead links exist in Cron/broadcast messages: returns None (Fail-Closed HOLD).
        - If dead links exist in interactive chats: appends dead-link warning note.
        """
        if not self._enabled or not msg.content:
            return msg

        all_alive, probe_results = await self.check_message(msg)
        if all_alive:
            return msg

        dead_links = [r for r in probe_results if not r.is_alive]
        dead_summary = ", ".join(f"{r.url} ({r.error or 'unreachable'})" for r in dead_links)

        is_cron = bool(msg.metadata and (msg.metadata.get("cron_context") or msg.metadata.get("job_id")))
        is_broadcast = bool(msg.metadata and msg.metadata.get("broadcast"))

        if is_cron or is_broadcast:
            logger.warning(
                "Outbound content gate HOLD fail-closed on channel '%s' (cron=%s, broadcast=%s): %s",
                msg.channel,
                is_cron,
                is_broadcast,
                dead_summary,
            )
            return None

        # Interactive chat: annotate with warning rather than blocking
        locale = get_locale_from_metadata(msg.metadata)
        warning_tmpl = channel_t(locale, "outbound_dead_link_warning")
        if warning_tmpl == "outbound_dead_link_warning":
            warning_tmpl = "⚠️ [Note: The following reference link may be unreachable: {url}]"

        dead_urls_str = ", ".join(r.url for r in dead_links)
        if "{url}" in warning_tmpl:
            warning_note = f"\n\n{warning_tmpl.format(url=dead_urls_str)}"
        else:
            warning_note = f"\n\n{warning_tmpl}{dead_urls_str}]"

        return dataclasses.replace(
            msg,
            content=msg.content + warning_note,
        )


_global_outbound_gate: OutboundContentGate | None = None


def get_outbound_content_gate() -> OutboundContentGate:
    """Retrieve the global OutboundContentGate singleton."""
    global _global_outbound_gate
    if _global_outbound_gate is None:
        _global_outbound_gate = OutboundContentGate()
    return _global_outbound_gate
