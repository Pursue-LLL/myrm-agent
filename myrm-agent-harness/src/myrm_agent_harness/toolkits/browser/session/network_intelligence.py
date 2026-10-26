"""CDP-based network intelligence: how each API request ended, and on-demand response bodies.

[INPUT]
- patchright.async_api::Page (POS: Playwright page instance)
- patchright.async_api::CDPSession (POS: Chrome DevTools Protocol session)
- utils.page_health::detach_cdp_bounded (POS: bounded browser and page health primitives)

[OUTPUT]
- NetworkIntelligence: CDP-based lazy response body retrieval; numbers API requests and tells how each one ended
- CdpRequestRecord: one tracked request, `seq` being the number network_log shows for it

[POS]
Provides Agent-accessible API intelligence layer that captures requestIds via CDP
Network domain events, records how each request ended, and offers on-demand response
body retrieval using Network.getResponseBody. Cooperates with NetworkLogger (which handles
synchronous metadata) — this component handles asynchronous CDP queries.
A request is `[pending]` only while it is really in flight: a redirect hop takes the status of the response that sent
the browser on (Chrome reuses the requestId across hops and reports that response with the next hop), and a request the
browser gave up on (blocked, refused, CORS, aborted before any answer, cut off mid-transfer) carries the browser's error,
so the model never waits on an answer that cannot come. A response the page itself dropped after it arrived (an empty
body nobody read, an aborted stream: Chrome reports `canceled`) keeps the status the server gave. The one exception is a
request a navigation cuts off before its headers: Chrome reports nothing for it, so it stays `[pending]`.
The number network_log shows is the request's own `seq`, handed out once in arrival order to XHR/Fetch requests,
not a position in the rolling window: the window drops its oldest records, so a position would name a different
request by the time the model asks for it. A number that is no longer tracked is refused, never re-pointed.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, TypedDict

from myrm_agent_harness.core.security.redact import redact_sensitive_text

from ..utils.page_health import detach_cdp_bounded

if TYPE_CHECKING:
    from patchright.async_api import CDPSession, Page

logger = logging.getLogger(__name__)

_MAX_TRACKED_REQUESTS = 100
_API_RESOURCE_TYPES = ("XHR", "Fetch")
_BODY_PREVIEW_MAX_CHARS = 8000
# Redaction window before truncation: keeps a credential crossing a truncation
# boundary structurally intact long enough to be masked (aligned with
# NetworkLogger's preview-window design).
_RAW_PREVIEW_WINDOW = 4096
_BODY_RAW_WINDOW = 16384
EMPTY_RESPONSE = "Empty response"
# Responses of these statuses carry no body by definition, so there is nothing to ask Chrome for.
_BODYLESS_STATUSES = frozenset({204, 205, 304})
# Chrome's answer when it never kept (or no longer holds) the body: an unread empty response or an aborted stream.
_NO_BODY_KEPT_ERROR = "No data found for resource"
_BODY_NOT_KEPT = "Chrome kept no body for this request: it may still be loading, or the page dropped it"


class _CdpRequest(TypedDict, total=False):
    url: str
    method: str
    postData: str


class _CdpResponse(TypedDict, total=False):
    status: int
    mimeType: str


class _CdpRequestWillBeSent(TypedDict, total=False):
    requestId: str
    type: str
    request: _CdpRequest
    redirectResponse: _CdpResponse


class _CdpResponseReceived(TypedDict, total=False):
    requestId: str
    response: _CdpResponse


class _CdpCorsErrorStatus(TypedDict, total=False):
    corsError: str


class _CdpLoadingFailed(TypedDict, total=False):
    requestId: str
    errorText: str
    canceled: bool
    corsErrorStatus: _CdpCorsErrorStatus


@dataclass(frozen=True, slots=True)
class CdpRequestRecord:
    """Tracked CDP request with requestId for lazy body retrieval.

    Attributes:
        request_id: CDP-assigned request identifier for getResponseBody
        url: Request URL
        method: HTTP method
        resource_type: Network resource type (XHR, Fetch, Document, etc.)
        status: HTTP response status code; for a redirect hop, the status of the redirect it answered with
        mime_type: Response MIME type
        failure: The browser's error when the request ended without a usable response (e.g. net::ERR_BLOCKED_BY_CLIENT)
        post_data: Raw POST body window; get_summary redacts it before cutting it to the preview
        timestamp: Request time (monotonic)
        seq: The number network_log shows for an XHR/Fetch request, unique for the session; 0 for other types
    """

    request_id: str
    url: str
    method: str
    resource_type: str
    status: int | None = None
    mime_type: str | None = None
    failure: str | None = None
    post_data: str | None = None
    timestamp: float = 0.0
    seq: int = 0


class NetworkIntelligence:
    """CDP-based network intelligence for lazy response body retrieval.

    Unlike NetworkLogger (synchronous Playwright event callbacks for metadata),
    this component uses CDP Network domain to track requestIds and provides
    on-demand response body access via Network.getResponseBody.

    Memory model: Only stores requestId + metadata (~200 bytes per request).
    Response bodies are fetched lazily from Chrome's internal cache on demand,
    consuming zero additional memory until explicitly requested.
    """

    def __init__(self, max_requests: int = _MAX_TRACKED_REQUESTS) -> None:
        self._requests: deque[CdpRequestRecord] = deque(maxlen=max_requests)
        self._next_seq = 1
        self._cdp_session: CDPSession | None = None
        self._bound_page: Page | None = None
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """Whether CDP Network monitoring is active."""
        return self._enabled

    async def attach(self, page: Page) -> None:
        """Attach CDP Network monitoring to a page.

        Idempotent: re-attaching to the same page is a no-op.
        Attaching to a different page detaches from the previous one first.
        """
        if self._bound_page is page and self._enabled:
            return

        await self.detach()

        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.enable")

            cdp.on("Network.requestWillBeSent", self._on_request_will_be_sent)
            cdp.on("Network.responseReceived", self._on_response_received)
            cdp.on("Network.loadingFailed", self._on_loading_failed)

            self._cdp_session = cdp
            self._bound_page = page
            self._enabled = True
        except Exception as exc:
            logger.warning("NetworkIntelligence: attach failed (non-critical): %s", exc)
            self._enabled = False

    async def detach(self) -> None:
        """Detach CDP monitoring and release resources."""
        if self._cdp_session is not None:
            await detach_cdp_bounded(self._cdp_session)
            self._cdp_session = None
        self._bound_page = None
        self._enabled = False

    def _on_request_will_be_sent(self, params: _CdpRequestWillBeSent) -> None:
        """Handle CDP Network.requestWillBeSent event."""
        try:
            request = params.get("request", {})
            resource_type = params.get("type", "")

            if resource_type not in ("XHR", "Fetch", "Document"):
                return

            request_id = params.get("requestId", "")
            if not request_id:
                return

            redirect = params.get("redirectResponse")
            if redirect:
                # This request continues a redirect hop under the same requestId; the previous hop never gets a
                # responseReceived of its own, so the response that redirected is the only place its status appears.
                self._apply_response(request_id, redirect)

            post_data_raw = request.get("postData", "")
            # Keep the raw window: get_summary redacts it before cutting it to the preview, so a credential that
            # crosses the cut is still masked.
            post_data_original = post_data_raw[:_RAW_PREVIEW_WINDOW] if post_data_raw else None

            seq = 0
            if resource_type in _API_RESOURCE_TYPES:
                seq = self._next_seq
                self._next_seq += 1

            record = CdpRequestRecord(
                request_id=request_id,
                url=request.get("url", ""),
                method=request.get("method", "GET"),
                resource_type=resource_type,
                post_data=post_data_original,
                timestamp=time.time(),
                seq=seq,
            )
            self._requests.append(record)
        except Exception as exc:
            logger.debug("NetworkIntelligence: requestWillBeSent handler error: %s", exc)

    def _on_response_received(self, params: _CdpResponseReceived) -> None:
        """Handle CDP Network.responseReceived — update status and mime_type."""
        try:
            self._apply_response(params.get("requestId", ""), params.get("response", {}))
        except Exception as exc:
            logger.debug("NetworkIntelligence: responseReceived handler error: %s", exc)

    def _on_loading_failed(self, params: _CdpLoadingFailed) -> None:
        """Handle CDP Network.loadingFailed — the browser gave up on the request; keep the error it names."""
        try:
            index = self._latest_index(params.get("requestId", ""))
            if index is None:
                return
            record = self._requests[index]
            # Chrome reports `canceled` when the page dropped the request (ERR_ABORTED). Once the response had arrived
            # (an empty body nobody read, an aborted stream) the server's answer stands, so that is no failure.
            if params.get("canceled") and record.status:
                return
            reason = params.get("errorText") or "failed"
            cors = params.get("corsErrorStatus")
            cors_error = cors.get("corsError") if cors else None
            failure = f"{reason} (CORS: {cors_error})" if cors_error else reason
            self._requests[index] = replace(record, failure=failure)
        except Exception as exc:
            logger.debug("NetworkIntelligence: loadingFailed handler error: %s", exc)

    def _apply_response(self, request_id: str, response: _CdpResponse) -> None:
        """Record a response's status and mime type on the newest request of `request_id`."""
        index = self._latest_index(request_id)
        if index is not None:
            self._requests[index] = replace(
                self._requests[index], status=response.get("status"), mime_type=response.get("mimeType", "")
            )

    def _latest_index(self, request_id: str) -> int | None:
        """Position of the newest tracked request of `request_id` (the hop that is current under a redirect)."""
        for i in range(len(self._requests) - 1, -1, -1):
            if self._requests[i].request_id == request_id:
                return i
        return None

    def get_api_requests(self) -> list[CdpRequestRecord]:
        """Get all tracked XHR/Fetch requests (most recent last)."""
        return [r for r in self._requests if r.resource_type in _API_RESOURCE_TYPES]

    def find_api_request(self, index: int) -> CdpRequestRecord | None:
        """The tracked API request that network_log numbered `index`; None once it is no longer tracked."""
        if index < 1:  # records that carry no number (documents) are 0
            return None
        return next((r for r in self._requests if r.seq == index), None)

    def _redirect_successor(self, record: CdpRequestRecord) -> CdpRequestRecord | None:
        """The request that carries on from `record` after its redirect: Chrome keeps the requestId across hops."""
        return next((r for r in self._requests if r.request_id == record.request_id and r.seq > record.seq), None)

    def invalid_index_error(self, index: int) -> str:
        """The answer for a number that names no tracked API request, with the numbers that are valid now."""
        tracked = self.get_api_requests()
        if not tracked:
            return f"Error: Invalid index {index}. No API requests are tracked; run network_log to refresh."
        return (
            f"Error: Invalid index {index}. Valid range: {tracked[0].seq}-{tracked[-1].seq}; "
            "run network_log to see the current numbering."
        )

    async def get_response_body(self, index: int) -> str:
        """Get response body for a tracked request by its network_log number.

        Uses CDP Network.getResponseBody for lazy retrieval from Chrome's cache.
        Returns truncated body if it exceeds max chars to prevent token explosion.

        Args:
            index: the number network_log showed for the request

        Returns:
            Response body text, or what to read instead when the request has none: the request a redirect hop
            continued as, the browser's error for a request that failed, or the reason there is no body (empty,
            a status without one, not kept by Chrome); otherwise an error message
        """
        if self._cdp_session is None:
            return "Error: CDP session not available. Navigate to a page first."

        record = self.find_api_request(index)
        if record is None:
            return self.invalid_index_error(index)

        if record.failure:
            return f"Request failed: {record.failure}"
        successor = self._redirect_successor(record)
        if successor is not None:
            redirected = f"Redirected ({record.status})" if record.status else "Redirected"
            return f"{redirected}; the response is request #{successor.seq}"
        if record.status in _BODYLESS_STATUSES:
            return f"No response body (status {record.status})"

        try:
            result = await self._cdp_session.send(
                "Network.getResponseBody",
                {"requestId": record.request_id},
            )
            body: str = result.get("body", "")
            is_base64 = result.get("base64Encoded", False)

            if is_base64:
                return f"[Binary response, {len(body)} base64 chars] MIME: {record.mime_type or 'unknown'}"

            if not body:
                return EMPTY_RESPONSE
            if len(body) > _BODY_PREVIEW_MAX_CHARS:
                return (
                    f"{redact_sensitive_text(body[:_BODY_RAW_WINDOW])[:_BODY_PREVIEW_MAX_CHARS]}\n\n"
                    f"... [truncated, total {len(body)} chars] "
                    f"MIME: {record.mime_type or 'unknown'}"
                )
            return body

        except Exception as exc:
            error_msg = str(exc)
            if "No resource with given identifier found" in error_msg:
                return (
                    f"Error: Response body no longer available for request #{index} "
                    f"({record.method} {record.url}). "
                    "This happens when the page has navigated away. "
                    "Bodies are only available for the current page's requests."
                )
            if _NO_BODY_KEPT_ERROR in error_msg:
                return _BODY_NOT_KEPT
            return f"Error retrieving response body: {error_msg}"

    @staticmethod
    def _status_label(req: CdpRequestRecord) -> str:
        """How the request ended; `pending` only while it is really in flight (a failure outranks an earlier status)."""
        if req.failure:
            return f"failed: {req.failure}"
        return str(req.status) if req.status else "pending"

    def get_summary(self) -> str:
        """Get formatted summary of tracked API requests for Agent display."""
        api_requests = self.get_api_requests()
        if not api_requests:
            return ""

        lines: list[str] = []
        for req in api_requests:
            status_str = self._status_label(req)
            line = f"  {req.seq}. {req.method} {req.url} [{status_str}]"
            if req.post_data:
                # Redact the raw stored body before display so credentials never
                # reach the Agent via network_log.
                safe_post = redact_sensitive_text(req.post_data)[:200]
                line += f"\n     POST: {safe_post}"
            lines.append(line)

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all tracked requests."""
        self._requests.clear()
