"""Every public route owns a unique OpenAPI operation id.

[POS]
tests/architecture/test_openapi_operation_ids.py

[INPUT]
- tests.support.public_api_app: OpenAPI generation warnings for the full public API

[OUTPUT]
- Fails when a (method, path) is registered twice (the later handler is silently shadowed)
  or when one `api_route` serves several methods (its operation id collides with itself).
"""

from __future__ import annotations

from tests.support.public_api_app import public_api_openapi


def test_openapi_operation_ids_are_unique() -> None:
    duplicates = public_api_openapi().duplicate_operation_ids
    assert not duplicates, (
        "duplicate OpenAPI operation ids (shadowed handler or multi-method api_route; "
        "register one route per method and keep a single handler per path):\n" + "\n".join(duplicates)
    )
