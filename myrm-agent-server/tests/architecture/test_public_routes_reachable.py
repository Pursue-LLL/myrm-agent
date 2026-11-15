"""Every public route is served by its own handler: no route registered earlier takes its requests.

[POS]
tests/architecture/test_public_routes_reachable.py

[INPUT]
- tests.support.public_api_app: the public API's route table in registration order

[OUTPUT]
- Fails when a route's own request is answered by an earlier route, as `GET /files/artifacts/shares` is when
  `/files/artifacts/{artifact_id}` is registered first. The fix is the registration order: the literal path goes first.
"""

from __future__ import annotations

from tests.support.public_api_app import public_api_unreachable_routes


def test_every_public_route_is_served_by_its_own_handler() -> None:
    unreachable = public_api_unreachable_routes()
    assert not unreachable, (
        "routes that an earlier route answers instead (register the literal path before the one with a path "
        "parameter):\n" + "\n".join(unreachable)
    )
