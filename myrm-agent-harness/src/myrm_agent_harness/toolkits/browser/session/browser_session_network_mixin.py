"""BrowserSession console and network log APIs.

[INPUT]
- session.console_logger::ConsoleLogger (POS: browser console capture)
- session.network_logger::NetworkLogger (POS: network request log capture)
- session.network_intelligence::NetworkIntelligence (POS: CDP-based API response body retrieval)
- pool.config::BrowserEngine (POS: which engine a session runs on decides whether the console can be captured)

[OUTPUT]
- BrowserSessionNetworkMixin: get_console_log / get_network_log / get_network_detail / replay_network_request.
- CONSOLE_CAPTURE_UNAVAILABLE: the answer `get_console_log` gives where the engine reports no console output.

[POS]
Console and network introspection APIs for BrowserSession. Delegates to NetworkLogger and
NetworkIntelligence; replay re-sends a GET by in-page fetch via the active tab and refuses every other
method (a recorded write is an action the page already performed: re-sending it would perform it again with
the user's cookies and nobody's approval, and it is the same capability evaluate gates behind a person).
The default Chromium engine never reports console output (its driver keeps `Console.enable` off to stay
undetectable), so `get_console_log` says so there: an empty log would read as "the page has no errors".
"""

from __future__ import annotations

import json

from myrm_agent_harness.core.security.redact import redact_sensitive_text

from ..pool.config import BrowserEngine
from .session_host import SessionHost

# Replay response bounds: the JS side returns a wider window so a credential
# crossing the final output cut stays structurally intact for redaction.
_REPLAY_RAW_WINDOW = 16000
_REPLAY_OUTPUT_MAX = 8000
_REPLAY_ERROR_MAX = 160

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

    def get_network_log(self, filter_mode: str = "api") -> str:
        """Get network request logs."""
        api_summary = self._network_intelligence.get_summary()

        if api_summary and filter_mode == "api":
            parts = [
                "API Requests (use network_detail with index to view response body):",
                api_summary,
            ]
            failed_summary = self._network_logger.get_summary("failed")
            if "No network requests" not in failed_summary:
                parts.append(f"\n{failed_summary}")
            return "\n".join(parts)

        summary = self._network_logger.get_summary(filter_mode)
        if api_summary:
            summary += f"\n\nAPI Requests (use network_detail with index to view response body):\n{api_summary}"
        return summary

    async def get_network_detail(self, index: int) -> str:
        """Get response body for a tracked API request by its network_log number."""
        return await self._network_intelligence.get_response_body(index)

    async def replay_network_request(self, index: int) -> str:
        """Re-send the GET request network_log numbered `index` from the active tab (in-page fetch).

        Only a GET is replayed: a recorded POST/PUT/PATCH/DELETE was an action the page already performed, so
        sending it again would perform it again with the user's cookies and without anyone's approval. The
        refusal names the method and nothing else (the URL is already in network_log; it may carry a token).
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

        js_code = f"""
            async () => {{
                const resp = await fetch({json.dumps(record.url)});
                const text = await resp.text();
                return text.substring(0, {_REPLAY_RAW_WINDOW});
            }}
        """

        try:
            result = await page.evaluate(js_code)
        except Exception as exc:
            return f"Error replaying request: {_failure_reason(exc)}"
        raw = str(result) if result else ""
        if not raw:
            return "Empty response"
        return redact_sensitive_text(raw)[:_REPLAY_OUTPUT_MAX]
