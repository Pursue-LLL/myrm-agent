"""Every schema `$ref` in the public API OpenAPI snapshot resolves to a component.

[POS]
tests/architecture/test_openapi_schema_refs.py

[INPUT]
- tests.support.public_api_app: the public API as OpenAPI, generated once per process (the routers `app.main` mounts
  itself, such as `/mem0`, `/v1` and the internal sync routes, are not part of it)

[OUTPUT]
- Fails when a request or response model could not be turned into a JSON schema (FastAPI then leaves a `$ref` to a
  component that is never emitted, so `/openapi.json` and Swagger UI cannot resolve that operation's body).
"""

from __future__ import annotations

from tests.support.public_api_app import public_api_openapi


def test_openapi_schema_refs_all_resolve() -> None:
    unresolved = public_api_openapi().unresolved_schema_refs
    assert not unresolved, (
        "OpenAPI `$ref` targets missing from components.schemas (only a field that the server alone injects and a "
        "client never sends, such as an arbitrary class, may be hidden with SkipJsonSchema):\n" + "\n".join(unresolved)
    )
