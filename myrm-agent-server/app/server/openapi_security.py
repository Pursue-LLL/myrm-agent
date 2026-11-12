"""OpenAPI security scheme injection for Swagger UI Authorize button.

[INPUT]
- fastapi.FastAPI (POS: app instance to attach custom openapi generator)

[OUTPUT]
- enrich_openapi_schema(): inject bearerAuth into an OpenAPI dict
- install_custom_openapi(): attach cached generator to a FastAPI app (optionally preparing the route table first)
- OPENAPI_API_DESCRIPTION: shared API docs body for main + tests

[POS]
Server-layer OpenAPI customization. Keeps app.main slim; tests import this module
without pulling the full dependency stack.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

OPENAPI_API_DESCRIPTION = """\
AI Agent backend service powering the MyrmAgent platform.

## Authentication

| Deploy mode | How it works |
|---|---|
| **Local / Tauri** | Loopback requests (127.0.0.1) are auto-trusted — no token needed. |
| **WebUI Remote** | Browser session cookie is sent automatically after login. |
| **Sandbox / API Key** | Pass your `SANDBOX_API_KEY` via `Authorization: Bearer <key>` or `X-Sandbox-Api-Key` header. |

## Compatible APIs

- **OpenAI-compatible**: `POST /v1/chat/completions`, `GET /v1/models`
- **Mem0-compatible**: `/mem0/*` endpoints
"""

_BEARER_AUTH_SCHEME: dict[str, object] = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "API Key",
    "description": (
        "Sandbox API Key or Bearer token. "
        "Pass via `Authorization: Bearer <key>` header. "
        "Also accepted in the `X-Sandbox-Api-Key` header."
    ),
}


def enrich_openapi_schema(schema: dict[str, object]) -> dict[str, object]:
    """Inject bearerAuth security scheme and global security requirement."""
    components = schema.setdefault("components", {})
    if not isinstance(components, dict):
        components = {}
        schema["components"] = components
    security_schemes = components.setdefault("securitySchemes", {})
    if isinstance(security_schemes, dict):
        security_schemes["bearerAuth"] = _BEARER_AUTH_SCHEME
    schema["security"] = [{"bearerAuth": []}]
    return schema


def install_custom_openapi(app: FastAPI, prepare: Callable[[], None] | None = None) -> None:
    """Attach cached custom OpenAPI generator (bearerAuth) to a FastAPI app.

    ``prepare`` runs before the schema is generated, so routes mounted on demand are part of it.
    """

    def _custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        if prepare is not None:
            prepare()
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        app.openapi_schema = enrich_openapi_schema(schema)
        return app.openapi_schema

    # FastAPI resolves ``openapi`` on the instance first; the instance dict is the typed way to shadow the method.
    vars(app)["openapi"] = _custom_openapi
