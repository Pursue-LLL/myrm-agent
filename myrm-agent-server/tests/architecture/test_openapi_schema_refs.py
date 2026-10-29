"""Every schema `$ref` in the public OpenAPI document resolves to a component.

[POS]
tests/architecture/test_openapi_schema_refs.py

[INPUT]
- tests.support.public_api_app: the full public API as OpenAPI, generated once per process

[OUTPUT]
- Fails when a request or response model could not be turned into a JSON schema (FastAPI then leaves a `$ref` to a
  component that is never emitted, so `/openapi.json` and Swagger UI cannot resolve that operation's body).
"""

from __future__ import annotations

from tests.support.public_api_app import public_api_openapi


def test_openapi_schema_refs_all_resolve() -> None:
    unresolved = public_api_openapi().unresolved_schema_refs
    assert not unresolved, (
        "OpenAPI `$ref` targets missing from components.schemas (a model with a non-JSON field type such as an "
        "arbitrary class must hide it with SkipJsonSchema):\n" + "\n".join(unresolved)
    )
