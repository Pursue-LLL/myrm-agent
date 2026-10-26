"""BrowserSession console and network log APIs.

[INPUT]
- session.console_logger::ConsoleLogger (POS: browser console capture)
- session.network_logger::NetworkLogger (POS: network request log capture)
- session.network_intelligence::NetworkIntelligence (POS: CDP-based API request outcomes and lazy response bodies)
- session.network_logger::safe_preview (POS: credential-masked text cut to a limit)
- pool.config::BrowserEngine (POS: which engine a session runs on decides whether the console can be captured)

[OUTPUT]
- BrowserSessionNetworkMixin: get_console_log / get_network_log / get_network_detail / replay_network_request.
- CONSOLE_CAPTURE_UNAVAILABLE: the answer `get_console_log` gives where the engine reports no console output.

[POS]
Console and network introspection APIs for BrowserSession. Delegates to NetworkLogger and
NetworkIntelligence. network_log is one list of numbered XHR/Fetch requests, whose number network_detail and
network_replay take, followed by the other resources that answered 4xx/5xx: those carry no number, because only
an XHR/Fetch response body can be opened, and they are listed even when no XHR/Fetch request exists (a white page
whose script 404s). A URL the list cut is given in full at the top of its network_detail answer.
Replay re-sends a GET by in-page fetch via the active tab and refuses every other
method (a recorded write is an action the page already performed: re-sending it would perform it again with
the user's cookies and nobody's approval, and it is the same capability evaluate gates behind a person).
The fetch is bounded in the page: the body is read as a stream and cut at a window (a huge or endless body is never
held whole), and a server that stops answering is aborted after `_REPLAY_TIMEOUT_S`, keeping what arrived.
The replay answer opens with the status the replay got (`[HTTP 401]`): the body alone cannot tell an empty 204 from
an empty 401. A replay re-sends the URL only, without the page's request headers, so when the page's own request
ended with another status the same line says so.
The default Chromium engine never reports console output (its driver keeps `Console.enable` off to stay
undetectable), so `get_console_log` says so there: an empty log would read as "the page has no errors".
"""

from __future__ import annotations

from myrm_agent_harness.core.security.redact import redact_sensitive_text

from ..pool.config import BrowserEngine
from .network_intelligence import EMPTY_RESPONSE, CdpRequestRecord
from .network_logger import URL_PREVIEW_CHARS, safe_preview
from .session_host import SessionHost

_API_LIST_HEADER = (
    "API Requests (use network_detail with index to view response body; "
    "a URL ending with … is cut here, network_detail gives it in full):"
)
_DETAIL_URL_MAX = 2000

# Replay response bounds: the JS side returns a wider window so a credential
# crossing the final output cut stays structurally intact for redaction.
_REPLAY_RAW_WINDOW = 16000
_REPLAY_OUTPUT_MAX = 8000
_REPLAY_ERROR_MAX = 160
_REPLAY_TIMEOUT_S = 20
# Runs in the page and answers [status, text, timedOut]; status stays 0 until the response headers arrive.
# The body is read as a stream and abandoned at the window, so a huge or endless body is never held whole;
# the abort at the timeout ends a server that stopped answering, keeping the part that did arrive.
_REPLAY_JS = """
async ([url, windowChars, timeoutMs]) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let status = 0;
    let text = '';
    let timedOut = false;
    try {
        const resp = await fetch(url, {signal: controller.signal});
        status = resp.status;
        if (resp.body) {
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            while (text.length < windowChars) {
                const {done, value} = await reader.read();
                if (done) break;
                text += decoder.decode(value, {stream: true});
            }
            reader.cancel().catch(() => {});
        }
    } catch (e) {
        if (e.name !== 'AbortError') throw e;
        timedOut = true;
    } finally {
        clearTimeout(timer);
    }
    return [status, text.substring(0, windowChars), timedOut];
}
"""

CONSOLE_CAPTURE_UNAVAILABLE = (
    "Console capture is unavailable in this browser mode, so an empty console cannot be assumed. "
    "Use network_log for failed requests or evaluate to inspect page state."
)


def _failure_reason(exc: Exception) -> str:
    """Why an in-page call failed: the driver's first line (it appends the page-side stack), redacted and bounded."""
    lines = str(exc).strip().splitlines()
    return redact_sensitive_text(lines[0])[:_REPLAY_ERROR_MAX] if lines else type(exc).__name__


class BrowserSessionNetworkMixin(SessionHost):
    def get_console_log(self) -> str:
        """Get captured browser console messages (errors, warnings, logs)."""
        engine = self._engine_preference or self._browser_pool.config.engine
        if engine == BrowserEngine.CHROMIUM_PATCHRIGHT:
            return CONSOLE_CAPTURE_UNAVAILABLE
        return self._console_logger.get_summary()

    def get_network_log(self) -> str:
        """The numbered XHR/Fetch requests, then the other resources that failed (listed even with no XHR/Fetch)."""
        api_summary = self._network_intelligence.get_summary()
        # Without CDP (Firefox) the driver's own list stands in, numbered by position.
        parts = [_API_LIST_HEADER, api_summary] if api_summary else [self._network_logger.get_summary()]
        failed_summary = self._network_logger.get_failed_summary()
        if failed_summary:
            parts.append(f"\n{failed_summary}")
        return "\n".join(parts)

    async def get_network_detail(self, index: int) -> str:
        """Get response body for a tracked API request by its network_log number.

        A URL that network_log cut comes first, in full: the list is the only other place the model has seen it.
        """
        record = self._network_intelligence.find_api_request(index)
        answer = await self._network_intelligence.get_response_body(index)
        if record is None:
            return answer
        full_url = safe_preview(record.url, _DETAIL_URL_MAX)
        if full_url == safe_preview(record.url, URL_PREVIEW_CHARS):
            return answer
        return f"URL: {full_url}\n{answer}"

    def _replay_status_line(self, record: CdpRequestRecord, status: int) -> str:
        """`[HTTP n]` for the replay, plus a note when the page's own request ended with another status."""
        line = f"[HTTP {status}]"
        page_status = self._network_intelligence.final_status(record)
        if page_status and page_status != status:
            line += (
                f" the page's own request got {page_status};"
                " replay re-sends the URL only, without the page's request headers"
            )
        return line

    async def replay_network_request(self, index: int) -> str:
        """Re-send the GET request network_log numbered `index` from the active tab (in-page fetch).

        Only a GET is replayed: a recorded POST/PUT/PATCH/DELETE was an action the page already performed, so
        sending it again would perform it again with the user's cookies and without anyone's approval. The
        refusal names the method and nothing else (the URL is already in network_log; it may carry a token).

        The answer is the status line (`[HTTP n]`), then the redacted body or `Empty response`. A server that
        stops answering ends the replay after `_REPLAY_TIMEOUT_S`: the part that arrived is returned and the
        answer says it is partial; with nothing received the answer is an error.
        """
        record = self._network_intelligence.find_api_request(index)
        if record is None:
            return self._network_intelligence.invalid_index_error(index)
        if record.method != "GET":
            return (
                f"Error: network_replay re-sends GET requests only; request #{index} is {record.method}. "
                "Perform that action on the page instead."
            )

        await self._ensure_components()
        page = self._tab_controller.get_active_page()

        try:
            reply = await page.evaluate(_REPLAY_JS, [record.url, _REPLAY_RAW_WINDOW, _REPLAY_TIMEOUT_S * 1000])
            status, text, timed_out = int(reply[0]), str(reply[1]), bool(reply[2])
        except Exception as exc:
            return f"Error replaying request: {_failure_reason(exc)}"
        if timed_out and not status:
            return f"Error replaying request: no response within {_REPLAY_TIMEOUT_S} s"
        body = redact_sensitive_text(text)[:_REPLAY_OUTPUT_MAX] if text else EMPTY_RESPONSE
        partial = f"\nStopped after {_REPLAY_TIMEOUT_S} s: the body is partial." if timed_out else ""
        return f"{self._replay_status_line(record, status)}{partial}\n{body}"
