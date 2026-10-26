"""Request text sanitizer middleware.

Strips control characters and invalid Unicode from inbound user text:
1. Query parameters (all methods)
2. JSON bodies (POST/PUT/PATCH; ``application/json`` and ``application/*+json``)
3. URL-encoded form bodies (POST/PUT/PATCH)

Only the harness ``strip_control_chars`` primitive runs here. Markup such as
``<think>`` or ``<function_calls>`` is user content (a pasted parser snippet, a
system prompt) and passes through unchanged; the tag filters of
``sanitize_text`` belong to the model-output pipeline.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlencode

from fastapi import Request, Response
from myrm_agent_harness.utils.text_sanitizer import strip_control_chars
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

_FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"


def _media_type(content_type: str) -> str:
    """Return the lower-cased media type without parameters such as ``charset``."""
    return content_type.split(";", 1)[0].strip().lower()


def _is_json_media_type(media_type: str) -> bool:
    """Mirror FastAPI's JSON body detection: ``application/json`` and ``application/*+json``."""
    return media_type == "application/json" or (media_type.startswith("application/") and media_type.endswith("+json"))


def _sanitize_json(value: JsonValue) -> JsonValue:
    """Strip control characters from every string value, at any nesting depth."""
    if isinstance(value, str):
        return strip_control_chars(value)
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_json(item) for key, item in value.items()}
    return value


def _sanitize_urlencoded(raw: bytes) -> bytes:
    """Strip control characters from the values of a URL-encoded query string or form body."""
    parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    cleaned = {key: [strip_control_chars(value) for value in values] for key, values in parsed.items()}
    return urlencode(cleaned, doseq=True).encode("utf-8")


class TextSanitizerMiddleware(BaseHTTPMiddleware):
    """Strip control characters from query strings and JSON / form bodies before routing.

    Defense in depth against corrupted input that would break JSON
    serialization, database writes or WebSocket frames. Removes C0/C1 control
    characters, unpaired surrogates, U+FFFD and model control tokens
    (``<|…|>``); everything else, tags included, is left as the user wrote it.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        query_string = request.scope.get("query_string", b"")
        if query_string:
            request.scope["query_string"] = _sanitize_urlencoded(query_string)

        if request.method in ("POST", "PUT", "PATCH"):
            media_type = _media_type(request.headers.get("content-type", ""))
            if _is_json_media_type(media_type):
                await self._sanitize_json_body(request)
            elif media_type == _FORM_MEDIA_TYPE:
                body = await request.body()
                if body:
                    request._body = _sanitize_urlencoded(body)

        return await call_next(request)

    @staticmethod
    async def _sanitize_json_body(request: Request) -> None:
        """Replace the cached request body with its sanitized JSON; bodies that are not JSON containers pass through."""
        body = await request.body()
        if not body:
            return
        try:
            data: JsonValue = json.loads(body)
            if not isinstance(data, dict | list):
                return
            cleaned = json.dumps(_sanitize_json(data)).encode("utf-8")
        except (ValueError, RecursionError) as exc:
            # Malformed, over-long integer or too deeply nested: the route's own validation reports it.
            logger.warning("Skipping JSON body sanitization: %s", exc)
            return
        # Starlette caches the body on the request, so downstream parsers read the sanitized payload.
        request._body = cleaned
