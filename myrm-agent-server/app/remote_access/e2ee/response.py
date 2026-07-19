"""Encrypt JSON API payloads for active E2EE sessions.

[INPUT]
- JSON-serializable response data + E2EE session context

[OUTPUT]
- Encrypted response payload (base64 bundle)

[POS]
Response encryption helper. Used by API endpoints returning data to E2EE clients.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.database.standard_responses import create_success_response
from app.remote_access.e2ee.session import E2EE_CONTENT_TYPE, E2EESession


def get_request_e2ee_session(request: Request) -> E2EESession | None:
    session = getattr(request.state, "e2ee_session", None)
    if isinstance(session, E2EESession):
        return session
    return None


def e2ee_success_response(request: Request, data: object = None, *, status_code: int = 200) -> JSONResponse:
    """Return standard success envelope, encrypted when an E2EE session is active."""
    payload: dict[str, Any] = create_success_response(data=data).model_dump(mode="json")
    session = get_request_e2ee_session(request)
    if session is None:
        return JSONResponse(status_code=status_code, content=payload)
    plain = json.dumps(payload, separators=(",", ":"))
    cipher = session.encrypt_text(plain)
    return JSONResponse(
        status_code=status_code,
        content={"v": 1, "c": cipher},
        media_type=E2EE_CONTENT_TYPE,
    )


__all__ = ["e2ee_success_response", "get_request_e2ee_session"]
