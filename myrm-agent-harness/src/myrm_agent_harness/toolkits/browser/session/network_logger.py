"""Network request logger for Agent diagnostics.


[INPUT]
- patchright.async_api::Page (POS: Playwright page instance)
- patchright.async_api::Request (POS: Playwright request object)
- patchright.async_api::Response (POS: Playwright response object)

[OUTPUT]
- RequestInfo: Immutable request/response record
- NetworkLogger: Synchronous network request capture and formatting
- URL_PREVIEW_CHARS / POST_PREVIEW_CHARS: How much of a URL / POST body a list line shows
- RAW_PREVIEW_WINDOW: How much raw text is kept, and masked, before that cut
- safe_preview: Credential-masked text cut to a limit (mask first, then cut)

[POS]
Network request logging for the browser toolkit. Provides self-diagnosis capability for browser session network activity:
the XHR/Fetch list of engines without CDP, and the one-line-per-request list of the other resources that answered 4xx/5xx
(unnumbered: their response body is never opened).

"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from myrm_agent_harness.core.security.redact import redact_sensitive_text

if TYPE_CHECKING:
    from patchright.async_api import Page, Request, Response

logger = logging.getLogger(__name__)

_STATIC_RESOURCE_TYPES = frozenset({"image", "stylesheet", "font", "media"})
# What a list line shows of a URL / POST body; network_detail gives a cut URL back in full.
URL_PREVIEW_CHARS = 160
POST_PREVIEW_CHARS = 80
_MAX_LISTED = 20
# Bounded window over the text passed to redaction. Redaction runs before the
# preview cut so a credential split by that cut stays masked; the window keeps
# event-callback latency bounded on large upload bodies while always covering
# the preview and its enclosing JSON structure.
RAW_PREVIEW_WINDOW = 4096
_BINARY_BODY = "<binary body>"


def safe_preview(text: str, limit: int) -> str:
    """Return ``text`` with credentials masked, cut to ``limit`` characters (a cut ends with ``…``)."""
    masked = redact_sensitive_text(text[:RAW_PREVIEW_WINDOW])
    return masked if len(masked) <= limit else f"{masked[: limit - 1]}…"


@dataclass(frozen=True, slots=True)
class RequestInfo:
    """Immutable record of a network request/response.

    Attributes:
        method: HTTP method (GET/POST/etc.)
        url: Request URL
        resource_type: Playwright resource type (document/xhr/fetch/etc.)
        timestamp: Request start time (unix timestamp)
        status: HTTP status code (None if request failed)
        status_text: HTTP status text (e.g., "OK", "Not Found")
        duration_ms: Request duration in milliseconds
        post_data_preview: Start of the POST body (credential-masked before the preview cut)
    """

    method: str
    url: str
    resource_type: str
    timestamp: float
    status: int | None = None
    status_text: str | None = None
    duration_ms: float | None = None
    post_data_preview: str | None = None

    @property
    def is_api_request(self) -> bool:
        """Whether this is an API request (XHR/Fetch)."""
        return self.resource_type in ("xhr", "fetch")

    @property
    def is_failed(self) -> bool:
        """Whether this request failed (4xx/5xx status)."""
        return self.status is not None and self.status >= 400


class NetworkLogger:
    """Network request filtering and recording for agent diagnostics.

    Filters by resource type, limits entries with FIFO; callbacks run synchronously
    when Patchright dispatches page events. Uses WeakKeyDictionary with the Request
    as the key to record start times of pending matches.

    Does not use ``__slots__`` so Patchright can attach internal properties to the
    listener functions.
    """

    def __init__(self, max_requests: int = 50) -> None:
        """Initialize network logger.

        Args:
            max_requests: Maximum number of requests to store (FIFO)
        """
        self._requests: deque[RequestInfo] = deque(maxlen=max_requests)
        self._pending: WeakKeyDictionary[Request, float] = WeakKeyDictionary()
        self._bound_page: Page | None = None

    @property
    def bound_page(self) -> Page | None:
        """The page currently registered for listeners (aligned with the active tab, driven by BrowserSession)."""
        return self._bound_page

    def _cb_request(self, request: Request) -> None:
        self._on_request(request)

    def _cb_response(self, response: Response) -> None:
        self._on_response(response)

    def _cb_request_failed(self, request: Request) -> None:
        self._on_request_failed(request)

    def detach_page(self, page: Page) -> None:
        """Remove listeners from the given page; effective only when that page is the currently bound object."""
        if self._bound_page is not page:
            return
        try:
            page.remove_listener("request", self._cb_request)
            page.remove_listener("response", self._cb_response)
            page.remove_listener("requestfailed", self._cb_request_failed)
        except Exception as exc:
            logger.warning("NetworkLogger: detach_page failed: %s", exc)
        finally:
            if self._bound_page is page:
                self._bound_page = None
            self._pending.clear()

    def detach_current(self) -> None:
        """Remove listeners from the currently bound page (no-op if none)."""
        if self._bound_page is not None:
            self.detach_page(self._bound_page)

    def start_capture(self, page: Page) -> None:
        """Register network listeners on page; idempotent for the same page instance.

        Args:
            page: Patchright page instance
        """
        if self._bound_page is page:
            return
        if self._bound_page is not None:
            self.detach_page(self._bound_page)
        self._bound_page = page
        page.on("request", self._cb_request)
        page.on("response", self._cb_response)
        page.on("requestfailed", self._cb_request_failed)

    def stop_capture(self) -> None:
        """Detach listeners and clear pending entries; keep the already-completed queue ``_requests``."""
        self.detach_current()
        self._pending.clear()

    def _should_capture(self, resource_type: str) -> bool:
        """Whether to capture this resource type."""
        return resource_type not in _STATIC_RESOURCE_TYPES

    def _on_request(self, request: Request) -> None:
        """Handle request event."""
        try:
            if not self._should_capture(request.resource_type):
                return
            self._pending[request] = time.time()
        except Exception as exc:
            logger.warning("Failed to capture request: %s", exc)

    def _on_response(self, response: Response) -> None:
        """Handle response event."""
        try:
            request = response.request
            if request not in self._pending:
                return

            start_time = self._pending.pop(request)
            duration_ms = (time.time() - start_time) * 1000

            post_data_preview = self._post_data_preview(request) if request.method in ("POST", "PUT", "PATCH") else None

            info = RequestInfo(
                method=request.method,
                url=request.url,
                resource_type=request.resource_type,
                timestamp=start_time,
                status=response.status,
                status_text=response.status_text,
                duration_ms=duration_ms,
                post_data_preview=post_data_preview,
            )
            self._requests.append(info)

        except Exception as exc:
            logger.warning("Failed to capture response: %s", exc)

    @staticmethod
    def _post_data_preview(request: Request) -> str | None:
        """Start of the POST body; the driver raises for a body that is not UTF-8 text, which must not cost the record."""
        try:
            raw = request.post_data
        except UnicodeDecodeError:
            return _BINARY_BODY
        return safe_preview(raw, POST_PREVIEW_CHARS) if raw else None

    def _on_request_failed(self, request: Request) -> None:
        """Handle request failure event."""
        try:
            if request not in self._pending:
                return

            start_time = self._pending.pop(request)
            duration_ms = (time.time() - start_time) * 1000

            info = RequestInfo(
                method=request.method,
                url=request.url,
                resource_type=request.resource_type,
                timestamp=start_time,
                status=None,
                status_text="Request Failed",
                duration_ms=duration_ms,
            )
            self._requests.append(info)

        except Exception as exc:
            logger.warning("Failed to capture failed request: %s", exc)

    def get_summary(self) -> str:
        """Format the captured XHR/Fetch requests, newest last (the list an engine without CDP offers)."""
        api_requests = [r for r in self._requests if r.is_api_request]
        if not api_requests:
            return "No API requests captured."

        recent = api_requests[-_MAX_LISTED:]

        lines = [f"Network Log ({len(api_requests)} total, showing last {len(recent)}):"]
        for i, req in enumerate(recent, 1):
            lines.extend(self._format_request(req, i))

        return "\n".join(lines)

    def get_failed_summary(self) -> str:
        """Format the non-XHR/Fetch requests that answered 4xx/5xx, one line each, newest last; empty when none did.

        They carry no request number: network_detail opens XHR/Fetch bodies only, so a number
        would invite a call that cannot succeed.
        """
        failed = [r for r in self._requests if r.is_failed and not r.is_api_request]
        if not failed:
            return ""

        shown = failed[-_MAX_LISTED:]
        lines = ["Other failed requests (not numbered, so network_detail cannot open them):"]
        if len(failed) > len(shown):
            lines.append(f"  ({len(failed) - len(shown)} earlier not shown)")
        lines.extend(
            f"  {r.resource_type} {r.method} {safe_preview(r.url, URL_PREVIEW_CHARS)} [{r.status}]" for r in shown
        )
        return "\n".join(lines)

    def _format_request(self, req: RequestInfo, index: int) -> list[str]:
        """Format a single request for display.

        Args:
            req: Request info to format
            index: Display index number

        Returns:
            List of formatted lines for this request
        """
        parts = ["", f"{index}. {req.method} {req.url}"]

        if req.status is not None:
            status_marker = "OK" if req.status < 400 else "FAIL"
            parts.append(f"   [{status_marker}] Status: {req.status} {req.status_text or ''}")
        elif req.status_text:
            parts.append(f"   [FAIL] {req.status_text}")

        if req.duration_ms is not None:
            parts.append(f"   Duration: {req.duration_ms:.0f}ms")

        if req.post_data_preview:
            parts.append(f"   POST body: {req.post_data_preview}")

        return parts

    def clear(self) -> None:
        """Clear all captured requests and pending state."""
        self._requests.clear()
        self._pending.clear()

    def get_pending_count(self) -> int:
        """Get count of pending requests (for troubleshooting).

        Returns:
            Number of requests awaiting response
        """
        return len(self._pending)
