"""The failover health check asks the provider it is given, not an answer recalled from another one.

The failover manager runs this check on a cooled-down model before it routes traffic back to it. The real ChatLiteLLM runs
against two loopback providers, with the LiteLLM defaults the harness applies in production.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms import config as _production_defaults  # noqa: F401  # applies the defaults on import
from myrm_agent_harness.toolkits.llms.adapters.chat_model import ChatLiteLLM
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_harness.toolkits.llms.fallback.health_check import lightweight_health_check
from tests.mocks.llm_wire_server import FakeProviderServer, FakeReply, openai_text_stream

_REFUSAL = FakeReply(
    json.dumps(
        {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}}
    ).encode(),
    status=401,
    content_type="application/json",
)


@pytest.fixture(autouse=True)
def _loopback_without_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def _model_on(server: FakeProviderServer) -> ChatLiteLLM:
    return create_litellm_model(
        "openai/probe-model", base_url=f"{server.base_url}/v1", api_key="sk-offline", streaming=True
    )


async def test_a_refusing_endpoint_is_not_vouched_for_by_an_earlier_success() -> None:
    with (
        FakeProviderServer(lambda _body: FakeReply(openai_text_stream())) as accepting,
        FakeProviderServer(lambda _body: _REFUSAL) as refusing,
    ):
        healthy = await lightweight_health_check(_model_on(accepting))
        refused = await lightweight_health_check(_model_on(refusing))

    assert (healthy, refused) == (True, False)
    assert len(refusing.requests) == 1
