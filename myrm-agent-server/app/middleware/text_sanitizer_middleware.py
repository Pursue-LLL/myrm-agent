"""Text sanitizer middleware for automatic request sanitization.

Intercepts all HTTP requests and sanitizes:
1. Query parameters (all methods)
2. Request body - JSON (POST/PUT/PATCH)
3. Request body - Form data (POST/PUT/PATCH)

Removes surrogate characters, control characters, and other invalid Unicode.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import Request, Response
from myrm_agent_harness.utils.text_sanitizer import sanitize_text
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize all string values in a dictionary.

    Args:
        data: Dictionary to sanitize.

    Returns:
        Sanitized dictionary with all string values cleaned.
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = sanitize_text(value)
        elif isinstance(value, dict):
            result[key] = _sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = [
                _sanitize_dict(item) if isinstance(item, dict) else sanitize_text(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class TextSanitizerMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically sanitize request strings.

    Intercepts all HTTP requests and sanitizes:
    1. Query parameters (all methods) - removes surrogates from query strings
    2. Request body JSON (POST/PUT/PATCH) - recursively sanitizes fields
    3. Request body Form (POST/PUT/PATCH) - sanitizes form-urlencoded data

    This provides a defense-in-depth layer against malicious or corrupted
    input data that could cause JSON serialization failures, database errors,
    or WebSocket disconnections.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Sanitize query parameters for all requests
        query_string = request.scope.get("query_string", b"")
        if query_string:
            try:
                decoded = query_string.decode("utf-8", errors="replace")
                parsed = parse_qs(decoded, keep_blank_values=True)
                sanitized_params = {k: [sanitize_text(v) for v in vs] for k, vs in parsed.items()}
                sanitized_query_string = urlencode(sanitized_params, doseq=True).encode("utf-8")
                request.scope["query_string"] = sanitized_query_string
            except Exception as e:
                logger.warning(f"Failed to sanitize query params: {e}")

        # Sanitize request body for POST/PUT/PATCH
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")

            # Sanitize JSON body
            if content_type == "application/json":
                try:
                    body = await request.body()
                    if body:
                        data = json.loads(body)
                        if isinstance(data, dict):
                            sanitized_data = _sanitize_dict(data)
                            sanitized_body = json.dumps(sanitized_data).encode("utf-8")

                            # async def receive():
                            #     return {"type": "http.request", "body": sanitized_body}
                            # request._receive = receive
                            request._body = sanitized_body

                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning(f"Failed to sanitize JSON body: {e}")

            # Sanitize Form data body
            elif content_type == "application/x-www-form-urlencoded":
                try:
                    body = await request.body()
                    if body:
                        decoded = body.decode("utf-8", errors="replace")
                        parsed = parse_qs(decoded, keep_blank_values=True)
                        sanitized_params = {k: [sanitize_text(v) for v in vs] for k, vs in parsed.items()}
                        sanitized_body = urlencode(sanitized_params, doseq=True).encode("utf-8")

                        # async def receive():
                        #     return {"type": "http.request", "body": sanitized_body}
                        # request._receive = receive
                        request._body = sanitized_body

                except (UnicodeDecodeError, Exception) as e:
                    logger.warning(f"Failed to sanitize form data: {e}")

        return await call_next(request)
