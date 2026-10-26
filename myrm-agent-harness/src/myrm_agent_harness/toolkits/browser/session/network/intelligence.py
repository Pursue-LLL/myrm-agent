"""CDP-based network intelligence: how each API request ended, and on-demand response bodies.

[INPUT]
- patchright.async_api::Page (POS: Playwright page instance)
- patchright.async_api::CDPSession (POS: Chrome DevTools Protocol session)
- utils.page_health::detach_cdp_bounded (POS: bounded browser and page health primitives)
- core.security.redact::redact_sensitive_text (POS: credential masking of response bodies)
- network.logger::safe_preview, URL_PREVIEW_CHARS, POST_PREVIEW_CHARS, RAW_PREVIEW_WINDOW (POS: the masked, bounded previews the list lines share with the NetworkLogger list)
- network.records::CdpRequestRecord and the CDP event payload types (POS: the shapes this recorder reads and keeps)

[OUTPUT]
- NetworkIntelligence: CDP-based lazy response body retrieval; numbers the current page's API requests and tells how each one ended
- EMPTY_RESPONSE: the answer for a response whose body is empty (network_detail and network_replay use the same words)

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
Only XHR/Fetch requests are tracked: they are the ones whose response body network_detail can open. The number
network_log shows is the request's own `seq`, handed out once in arrival order, not a position in the rolling window:
the window drops its oldest records, so a position would name a different request by the time the model asks for it.
A number that is no longer tracked is refused, never re-pointed.
The list is the current page's: every record carries the `epoch` of the page it was made on, and the epoch moves on when
the main frame loads a new document (CDP `Page.frameNavigated`: a reload, back/forward and a link all fire it, a
`pushState` route change does not, exactly like DevTools without "Preserve log") and when the recorder attaches to
another page (a tab switch). Records of earlier pages stay in the window until it drops them but are neither listed nor
openable, so the model never reads another page's request as this page's. A response whose MIME type is an image,
audio, video or font is a file, not data: it leaves the window once it has answered and is only counted.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import replace
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.redact import redact_sensitive_text

from ...utils.page_health import detach_cdp_bounded
from .logger import POST_PREVIEW_CHARS, RAW_PREVIEW_WINDOW, URL_PREVIEW_CHARS, safe_preview
from .records import (
    CdpFrameNavigated,
    CdpLoadingFailed,
    CdpRequestRecord,
    CdpRequestWillBeSent,
    CdpResponse,
    CdpResponseReceived,
)

if TYPE_CHECKING:
    from patchright.async_api import CDPSession, Page

logger = logging.getLogger(__name__)

_MAX_TRACKED_REQUESTS = 100
_API_RESOURCE_TYPES = ("XHR", "Fetch")
_BODY_PREVIEW_MAX_CHARS = 8000
_BODY_RAW_WINDOW = 16384
EMPTY_RESPONSE = "Empty response"
# Responses of these types are files, not data: icons and fonts would fill the window and cannot be read as text.
_FILE_MIME_PREFIXES = ("image/", "audio/", "video/", "font/")
_NO_CDP_ERROR = (
    "Error: No CDP connection: response bodies cannot be read or replayed "
    "(Firefox-based engines have none; on Chromium open a page first)."
)
# Responses of these statuses carry no body by definition, so there is nothing to ask Chrome for.
_BODYLESS_STATUSES = frozenset({204, 205, 304})
# Chrome's answer when it never kept (or no longer holds) the body: an unread empty response or an aborted stream.
_NO_BODY_KEPT_ERROR = "No data found for resource"
_BODY_NOT_KEPT = "The browser kept no body for this request: it may still be loading, or the page dropped it"


def _compact_ranges(numbers: list[int]) -> str:
    """`[3, 4, 5, 8]` -> `3-5, 8`: the numbers an answer names, one range per run (hidden files leave gaps)."""
    runs: list[list[int]] = []
    for number in numbers:
        if runs and number == runs[-1][1] + 1:
            runs[-1][1] = number
        else:
            runs.append([number, number])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


class NetworkIntelligence:
    """CDP-based network intelligence for lazy response body retrieval.

    Unlike NetworkLogger (synchronous Playwright event callbacks for metadata),
    this component uses CDP Network domain to track requestIds and provides
    on-demand response body access via Network.getResponseBody.

    Memory model: only metadata per request (URL, status, a POST-body window of at most 4 KiB) in a rolling
    window of `_MAX_TRACKED_REQUESTS` requests. Response bodies are fetched lazily from Chrome's internal cache
    on demand, consuming zero additional memory until explicitly requested.
    """

    def __init__(self, max_requests: int = _MAX_TRACKED_REQUESTS) -> None:
        self._requests: deque[CdpRequestRecord] = deque(maxlen=max_requests)
        self._next_seq = 1
        self._epoch = 0
        self._files_hidden = 0
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
        # Another page starts here, whether or not the recorder manages to attach to it.
        self._begin_page()

        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.enable")
            await cdp.send("Page.enable")

            cdp.on("Network.requestWillBeSent", self._on_request_will_be_sent)
            cdp.on("Network.responseReceived", self._on_response_received)
            cdp.on("Network.loadingFailed", self._on_loading_failed)
            cdp.on("Page.frameNavigated", self._on_frame_navigated)

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

    def _begin_page(self) -> None:
        """A page's requests start here: everything recorded so far belongs to a page that is no longer the one shown."""
        self._epoch += 1
        self._files_hidden = 0

    def _on_frame_navigated(self, params: CdpFrameNavigated) -> None:
        """Handle CDP Page.frameNavigated: a new document in the main frame is a new page (a subframe is not)."""
        if not params.get("frame", {}).get("parentId"):
            self._begin_page()

    def _on_request_will_be_sent(self, params: CdpRequestWillBeSent) -> None:
        """Handle CDP Network.requestWillBeSent event."""
        try:
            request = params.get("request", {})
            resource_type = params.get("type", "")

            if resource_type not in _API_RESOURCE_TYPES:
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
            post_data_original = post_data_raw[:RAW_PREVIEW_WINDOW] if post_data_raw else None

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
                epoch=self._epoch,
            )
            self._requests.append(record)
        except Exception as exc:
            logger.debug("NetworkIntelligence: requestWillBeSent handler error: %s", exc)

    def _on_response_received(self, params: CdpResponseReceived) -> None:
        """Handle CDP Network.responseReceived — update status and mime_type."""
        try:
            self._apply_response(params.get("requestId", ""), params.get("response", {}))
        except Exception as exc:
            logger.debug("NetworkIntelligence: responseReceived handler error: %s", exc)

    def _on_loading_failed(self, params: CdpLoadingFailed) -> None:
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

    def _apply_response(self, request_id: str, response: CdpResponse) -> None:
        """Record a response's status and mime type on the newest request of `request_id`; a file only counts."""
        index = self._latest_index(request_id)
        if index is None:
            return
        record = self._requests[index]
        mime_type = response.get("mimeType", "")
        if mime_type.startswith(_FILE_MIME_PREFIXES):
            del self._requests[index]
            if record.epoch == self._epoch:
                self._files_hidden += 1
            return
        self._requests[index] = replace(record, status=response.get("status"), mime_type=mime_type)

    def _latest_index(self, request_id: str) -> int | None:
        """Position of the newest tracked request of `request_id` (the hop that is current under a redirect)."""
        for i in range(len(self._requests) - 1, -1, -1):
            if self._requests[i].request_id == request_id:
                return i
        return None

    def get_api_requests(self) -> list[CdpRequestRecord]:
        """The current page's tracked XHR/Fetch requests (most recent last)."""
        return [r for r in self._requests if r.epoch == self._epoch]

    def find_api_request(self, index: int) -> CdpRequestRecord | None:
        """The current page's API request that network_log numbered `index`; None once it is gone or from an earlier page."""
        return next((r for r in self.get_api_requests() if r.seq == index), None)

    def _redirect_successor(self, record: CdpRequestRecord) -> CdpRequestRecord | None:
        """The request that carries on from `record` after its redirect: Chrome keeps the requestId across hops."""
        return next((r for r in self._requests if r.request_id == record.request_id and r.seq > record.seq), None)

    def final_status(self, record: CdpRequestRecord) -> int | None:
        """The status the page got for `record`: that of the last hop when redirects carried the request on."""
        while (successor := self._redirect_successor(record)) is not None:
            record = successor
        return record.status

    def invalid_index_error(self, index: int) -> str:
        """The answer for a number that names no request of the current page, with the numbers that are valid now."""
        if self._cdp_session is None and not self._requests:
            # Nothing was ever recorded and nothing can record: an engine without CDP.
            return _NO_CDP_ERROR
        tracked = self.get_api_requests()
        if not tracked:
            return (
                f"Error: Invalid index {index}. No API requests are tracked on the current page; "
                "run network_log to refresh."
            )
        return (
            f"Error: Invalid index {index}. Valid range: {_compact_ranges([r.seq for r in tracked])}; "
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
            return _NO_CDP_ERROR

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
                    f"({record.method} {safe_preview(record.url, URL_PREVIEW_CHARS)}). "
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
        """Format the tracked API requests for network_log, a line each (empty when none is tracked).

        URL and POST body are cut to their previews; the cut is made after credentials are masked, so a
        credential the cut would split never reaches the Agent as a fragment.
        """
        lines: list[str] = []
        for req in self.get_api_requests():
            url = safe_preview(req.url, URL_PREVIEW_CHARS)
            line = f"  {req.seq}. {req.method} {url} [{self._status_label(req)}]"
            if req.post_data:
                line += f"\n     POST: {safe_preview(req.post_data, POST_PREVIEW_CHARS)}"
            lines.append(line)

        return "\n".join(lines)

    def hidden_summary(self) -> str:
        """What the list leaves out, in one line (empty when nothing is): earlier pages' requests and file responses."""
        left_out: list[str] = []
        if any(r.epoch != self._epoch for r in self._requests):
            left_out.append("requests of earlier pages")
        if self._files_hidden:
            left_out.append(f"{self._files_hidden} image, audio, video and font responses")
        return f"(not listed: {'; '.join(left_out)})" if left_out else ""

    def clear(self) -> None:
        """Clear all tracked requests."""
        self._requests.clear()
        self._files_hidden = 0
