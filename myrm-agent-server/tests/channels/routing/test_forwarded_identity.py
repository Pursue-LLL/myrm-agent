"""``forwarded_identity``: the one place a ``user_id`` a message carries is believed."""

from __future__ import annotations

import pytest

from app.channels.routing.policy_resolver_support import forwarded_identity
from app.channels.types import InboundMessage

_FORWARD = {"trusted_inbound": "control_plane"}


@pytest.mark.parametrize(
    ("user_id", "metadata", "expected"),
    [
        pytest.param("owner-1", _FORWARD, "owner-1", id="control-plane forward carrying an identity"),
        pytest.param(None, _FORWARD, None, id="forward without an identity"),
        pytest.param("", _FORWARD, None, id="forward with an empty identity"),
        pytest.param("owner-1", {}, None, id="identity without the mark"),
        pytest.param("owner-1", {"trusted_inbound": "local_connector"}, None, id="identity marked as another origin"),
    ],
)
def test_a_carried_identity_counts_only_from_a_control_plane_forward(
    user_id: str | None, metadata: dict[str, object], expected: str | None
) -> None:
    msg = InboundMessage(channel="discord", sender_id="u1", content="hi", user_id=user_id, metadata=metadata)

    assert forwarded_identity(msg) == expected
