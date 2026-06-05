"""Risk gate for agent stream input."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS, SSEEnvelope


async def check_stream_risk(
    text: str,
    chat_id: str | None,
) -> StreamingResponse | None:
    """Run risk detection on user input before processing.

    Returns a StreamingResponse with block-event SSE if blocked, else None.
    """
    if not text:
        return None

    from app.services.risk.detection import get_detection_service

    service = get_detection_service()
    if service.rule_count == 0:
        return None

    result = service.detect(text)
    if not result.matches:
        return None

    if result.blocked:
        trace_id = str(uuid.uuid4())
        from app.platform_utils import get_session_factory

        session_factory = get_session_factory()
        async with session_factory() as db:
            await service.record_hits(
                db,
                result.matches,
                trace_id=trace_id,
                session_id=chat_id,
            )
            await db.commit()

        rule_names = ", ".join(m.display_name for m in result.matches[:3])
        block_msg = f"Your message was blocked by risk policy ({rule_names}). Please revise and try again."

        async def _block_stream() -> AsyncGenerator[str, None]:
            event = {
                "type": "risk_blocked",
                "data": {
                    "message": block_msg,
                    "rules": [
                        {
                            "rule_id": m.rule_id,
                            "display_name": m.display_name,
                            "severity": m.severity,
                        }
                        for m in result.matches
                    ],
                },
            }
            yield SSEEnvelope.from_any(event).to_sse_chunk()

        return StreamingResponse(
            content=_block_stream(),
            media_type="text/event-stream",
            headers=SSE_RESPONSE_HEADERS,
        )
