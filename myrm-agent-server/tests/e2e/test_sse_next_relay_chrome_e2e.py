"""Chrome-lane E2E: a server-sent event stream reaches a browser through the Next.js server that relays ``/api/v1``.

A browser asks for ``Accept-Encoding: gzip`` and, in local mode, reaches the backend through the Next.js server's ``/api/v1``
rewrite. That server compresses what it may; a stream it compresses is held back until the compressor's buffer fills, so a quiet
stream (the attach a reloaded page opens on a run parked behind its approval card) delivers nothing until the page's idle timeout
cuts it. The backend's ``Cache-Control: no-transform`` is what keeps the relay from compressing an event stream.

The test is plain HTTP against the lane's UI origin: the page-level E2E runtime binds the page to the backend directly and never
goes through this relay, so only a request made like a browser's reaches it.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_sse_next_relay_chrome_e2e.py
"""

from __future__ import annotations

import httpx
import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url

# The stream sends its first event at once, so a few seconds is long for a relay that forwards it.
_FIRST_EVENT_WITHIN_SEC = 8.0
_STREAM_PATH = "/api/v1/notifications/stream"


def first_decoded_chunk(ui_origin: str) -> str:
    """The first decoded text of the event stream, asked for the way a browser asks; raises ``httpx.ReadTimeout`` if none comes."""
    with httpx.stream(
        "GET",
        f"{ui_origin.rstrip('/')}{_STREAM_PATH}",
        headers={"Accept": "text/event-stream", "Accept-Encoding": "gzip"},
        timeout=httpx.Timeout(15.0, read=_FIRST_EVENT_WITHIN_SEC),
    ) as response:
        assert response.status_code == 200, response.status_code
        return next(response.iter_text())


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_an_event_stream_is_not_held_back_by_the_next_relay_for_a_client_that_accepts_gzip() -> None:
    assert first_decoded_chunk(get_e2e_ui_url()).strip()
