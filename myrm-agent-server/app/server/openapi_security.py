"""OpenAPI security scheme injection for Swagger UI Authorize button."""

from __future__ import annotations

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


def install_custom_openapi(app: FastAPI) -> None:
    """Attach cached custom OpenAPI generator (bearerAuth) to a FastAPI app."""

    def _custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        app.openapi_schema = enrich_openapi_schema(schema)
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[method-assign]
