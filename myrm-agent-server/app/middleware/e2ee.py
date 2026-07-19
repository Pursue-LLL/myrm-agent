"""HTTP middleware: decrypt E2EE mobile remote requests before auth handlers.

[INPUT]
- FastAPI Request with optional X-E2EE-Session-Id header

[OUTPUT]
- Decrypted request body (transparent to downstream handlers)

[POS]
Middleware layer. Sits before auth handlers in the ASGI pipeline.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.remote_access.e2ee import (
    E2EECryptoError,
    E2EE_CONTENT_TYPE,
    E2EE_PAIR_CIPHERTEXT_HEADER,
    E2EE_PAIR_QUERY_PARAM,
    E2EE_SESSION_HEADER,
    E2EESession,
    get_e2ee_session_store,
    parse_encrypted_body,
)
from app.remote_access.mobile_gate import is_mobile_remote_control_path, is_mobile_remote_pairing_path

logger = logging.getLogger(__name__)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            stripped = value.strip()
            return stripped or None
    return None


async def _replace_request_body(request: Request, body: bytes) -> None:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # noqa: SLF001


class E2EEMiddleware(BaseHTTPMiddleware):
    """Decrypt pair tokens and JSON bodies for established E2EE mobile sessions."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        mobile_path = is_mobile_remote_control_path(path) or is_mobile_remote_pairing_path(path)
        if not mobile_path:
            return await call_next(request)

        session_id = _header_value(request.headers, E2EE_SESSION_HEADER)
        session = await get_e2ee_session_store().get(session_id)
        if session is None:
            return await call_next(request)

        request.state.e2ee_session_id = session.session_id
        request.state.e2ee_session = session

        try:
            await self._decrypt_pair_token(request, session)
            await self._decrypt_body_if_needed(request, session)
        except E2EECryptoError as exc:
            logger.warning("E2EE decrypt failed for %s: %s", path, exc)
            return JSONResponse(status_code=400, content={"detail": "E2EE decrypt failed"})

        await get_e2ee_session_store().refresh(session.session_id)
        return await call_next(request)

    async def _decrypt_pair_token(self, request: Request, session: E2EESession) -> None:
        encrypted_header = _header_value(request.headers, E2EE_PAIR_CIPHERTEXT_HEADER)
        encrypted_query = request.query_params.get(E2EE_PAIR_QUERY_PARAM)
        ciphertext = encrypted_header or encrypted_query
        if not ciphertext:
            return
        request.state.e2ee_pair_token = session.decrypt_text(ciphertext)

    async def _decrypt_body_if_needed(self, request: Request, session: E2EESession) -> None:
        if request.method not in {"POST", "PUT", "PATCH"}:
            return
        content_type = request.headers.get("content-type", "")
        if E2EE_CONTENT_TYPE not in content_type and "application/json" not in content_type:
            return
        raw = await request.body()
        if not raw:
            return
        if E2EE_CONTENT_TYPE in content_type:
            cipher = parse_encrypted_body(raw)
            plain = session.decrypt_text(cipher)
            await _replace_request_body(request, plain.encode("utf-8"))
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if isinstance(payload, dict) and isinstance(payload.get("c"), str):
            plain = session.decrypt_text(payload["c"])
            await _replace_request_body(request, plain.encode("utf-8"))


__all__ = ["E2EEMiddleware"]
