"""[INPUT]
- myrm_agent_harness.api.hooks::set_client_attribution (POS: process-wide registration with the model factory)
- app.core.brand::CLIENT_ATTRIBUTION (POS: the application identity announced to model gateways)

[OUTPUT]
- server_client_attribution(): context manager that registers the server's identity for the block and removes it after

[POS]
Tests that call ``create_chat_model`` directly never run the startup that registers the identity, so they register it
here around exactly the calls whose headers they assert. Calls that send real requests stay unregistered, so the product
is never announced to a real gateway from a test.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from myrm_agent_harness.api.hooks import set_client_attribution

from app.core.brand import CLIENT_ATTRIBUTION


@contextmanager
def server_client_attribution() -> Iterator[None]:
    set_client_attribution(CLIENT_ATTRIBUTION)
    try:
        yield
    finally:
        set_client_attribution(None)
