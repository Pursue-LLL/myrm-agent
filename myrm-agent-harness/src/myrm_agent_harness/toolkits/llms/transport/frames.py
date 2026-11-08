"""The payload of one stream frame (an SSE ``data:`` field or an NDJSON line).

[INPUT]
- transport.errors (POS: LLMResponseError for a payload that is cut off)

[OUTPUT]
- json_frame: the JSON object a frame carries, ``None`` for a frame that carries no payload

[POS]
Shared by every wire's stream decoder, so a frame a gateway puts between the payloads is treated the same on every
wire. A payload frame is always a JSON object; text that does not open one (a keep-alive word, an empty field,
``[DONE]``, a bracketed marker like ``[PING]``) carries no content and is skipped. A frame that opens an object but
does not parse is a payload that was cut or corrupted on the way: skipping it would drop content without a trace, so
it fails the stream and the caller's retry produces the whole answer again.
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError

logger = logging.getLogger(__name__)


def json_frame(provider: str, data: str) -> dict[str, object] | None:
    text = data.strip()
    if not text.startswith("{"):
        if text and text != "[DONE]":
            logger.debug("Skipping a stream frame without a payload from %s", provider)
        return None
    try:
        payload: dict[str, object] = json.loads(text)
    except ValueError as exc:
        # Worded away from "invalid JSON": the classifier reads that as a model that produced bad output.
        raise LLMResponseError(provider, f"{provider} sent a stream frame that is cut off or corrupted") from exc
    return payload
