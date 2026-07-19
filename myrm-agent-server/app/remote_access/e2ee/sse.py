"""SSE helpers: encrypt mobile attach stream chunks when E2EE session is active.

[INPUT]
- SSE event chunks + optional E2EE session

[OUTPUT]
- Encrypted SSE chunks (when E2EE active) or passthrough (when not)

[POS]
SSE encryption adapter. Wraps the SSE stream for E2EE mobile clients.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from app.remote_access.e2ee.session import E2EESession


async def encrypt_sse_stream(
    source: AsyncGenerator[str, None],
    session: E2EESession,
) -> AsyncGenerator[str, None]:
    """Wrap plaintext SSE chunks as encrypted ``e2ee_frame`` envelopes."""
    async for chunk in source:
        cipher = session.encrypt_text(chunk)
        payload = json.dumps({"v": 1, "c": cipher}, separators=(",", ":"))
        yield f"event: e2ee_frame\ndata: {payload}\n\n"


__all__ = ["encrypt_sse_stream"]
