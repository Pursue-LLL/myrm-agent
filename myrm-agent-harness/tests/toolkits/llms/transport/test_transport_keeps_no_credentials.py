"""A key belongs to the call that passed it: the transport keeps none between calls.

One shared transport serves every model and thread, so a key that outlived its call would be sent on the next caller's
request: another user's key, or a key the owner has since removed. Each case issues a call with a key and then one
without, against a provider double, and reads the credential that reached the provider.
"""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.llms.transport.client import get_transport
from myrm_agent_harness.toolkits.llms.transport.profile import PROFILES

from .gateway_bodies import answer
from .provider_double import BASE, Provider, json_response

_MESSAGES = [{"role": "user", "content": "hi"}]
_RESPONSE = {
    "status": "completed",
    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hello"}]}],
}


def _issue(call: str, api_key: str | None) -> None:
    transport = get_transport()
    params = {"model": "openai/gpt-4o-mini", "api_base": BASE, "api_key": api_key}
    if call == "completion":
        transport.completion(messages=_MESSAGES, **params)
    elif call == "acompletion":
        asyncio.run(transport.acompletion(messages=_MESSAGES, **params))
    elif call == "responses":
        transport.responses(input="hi", **params)
    else:
        asyncio.run(transport.aresponses(input="hi", **params))


def _credentials(provider: Provider) -> list[str | None]:
    return [request.headers.get("authorization") for request in provider.requests]


@pytest.fixture(autouse=True)
def no_key_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment is another source of keys; these cases are about the one a call passes."""
    for profile in PROFILES.values():
        for name in profile.api_key_env:
            monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("call", ["completion", "acompletion", "responses", "aresponses"])
def test_a_call_without_a_key_does_not_send_the_key_of_the_call_before(provider: Provider, call: str) -> None:
    provider.serves(json_response(_RESPONSE if "responses" in call else answer()))

    _issue(call, "first-callers-key")
    _issue(call, None)

    assert _credentials(provider) == ["Bearer first-callers-key", None]


def test_each_call_sends_the_key_it_was_given(provider: Provider) -> None:
    provider.serves(json_response(answer()))

    for key in ("key-a", "key-b", "key-a"):
        _issue("completion", key)

    assert _credentials(provider) == ["Bearer key-a", "Bearer key-b", "Bearer key-a"]
