"""The transport package resolves its names on first use and keeps the wires out of light import paths.

[INPUT]
- myrm_agent_harness.toolkits.llms.transport (POS: package under test)

[OUTPUT]
- Regression coverage: every exported name resolves to its defining module, and classifying a failure does not
  load the transport client.

[POS]
The failure classifier and the HTTP server's import path read error classes and provider routes; loading the
wires there would add start-up work to every launch.
"""

from __future__ import annotations

import subprocess
import sys

import myrm_agent_harness.toolkits.llms.transport as transport

_CLIENT_MODULE = "myrm_agent_harness.toolkits.llms.transport.client"


def test_every_exported_name_resolves() -> None:
    for name in transport.__all__:
        assert getattr(transport, name) is not None, name


def test_exports_are_the_defining_module_objects() -> None:
    from myrm_agent_harness.toolkits.llms.transport import client, errors, http, profile

    assert transport.get_transport is client.get_transport
    assert transport.LLMCallError is errors.LLMCallError
    assert transport.LLMHTTPError is errors.LLMHTTPError
    assert transport.aclose_clients is http.aclose_clients
    assert transport.resolve_route is profile.resolve_route


def test_the_package_lists_exactly_what_it_exports() -> None:
    assert dir(transport) == sorted(transport.__all__)


def test_an_unknown_name_is_an_attribute_error() -> None:
    try:
        transport.no_such_name  # noqa: B018 - the access is the assertion
    except AttributeError as exc:
        assert "no_such_name" in str(exc)
    else:
        raise AssertionError("an unknown name must raise AttributeError")


def _loaded_after(statement: str) -> bool:
    probe = f"import sys; {statement}; print({_CLIENT_MODULE!r} in sys.modules)"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    return result.stdout.strip() == "True"


def test_reading_an_error_class_or_a_route_does_not_load_the_client() -> None:
    assert not _loaded_after("from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError")
    assert not _loaded_after("from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route")
    assert not _loaded_after("from myrm_agent_harness.toolkits.llms.errors.classifier import classify_error")


def test_asking_for_the_transport_loads_the_client() -> None:
    assert _loaded_after("from myrm_agent_harness.toolkits.llms.transport import get_transport")
