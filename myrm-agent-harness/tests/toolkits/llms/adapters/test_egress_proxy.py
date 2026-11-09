"""A model's ``egress_proxy`` is the proxy its provider calls go through, in the form the HTTP client takes.

The call is addressed to a host that exists nowhere and a loopback proxy answers for it, so a reply proves the request
travelled through the proxy: no assertion on the parameters handed to the transport could show that.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model import TransportChatModel
from myrm_agent_harness.toolkits.llms.transport import http
from tests.support.forward_proxy import forward_proxy

_BASE = "http://llm.invalid/v1"
_COMPLETION = json.dumps(
    {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
).encode()


def _model(proxy: str | None) -> TransportChatModel:
    return TransportChatModel(model="openai/gpt-4o", api_base=_BASE, api_key="key", egress_proxy=proxy)


class TestConfiguredProxy:
    @pytest.mark.parametrize(
        ("configured", "used"),
        [
            ("http://proxy.test:3128", "http://proxy.test:3128"),
            (" socks://127.0.0.1:1080 ", "socks5://127.0.0.1:1080"),
        ],
    )
    def test_the_call_names_the_normalized_proxy(self, configured: str, used: str) -> None:
        assert _model(configured)._client_params["proxy"] == used

    @pytest.mark.parametrize("configured", [None, "", "   "])
    def test_no_proxy_is_no_option(self, configured: str | None) -> None:
        assert "proxy" not in _model(configured)._client_params


class TestCallsGoThroughTheProxy:
    def test_a_sync_call(self) -> None:
        with forward_proxy(_COMPLETION) as proxy:
            try:
                reply = _model(proxy.url).invoke("hi")
            finally:
                asyncio.run(http.aclose_clients())

            assert reply.content == "ok"
            assert proxy.targets == [f"{_BASE}/chat/completions"]

    async def test_an_async_call(self) -> None:
        with forward_proxy(_COMPLETION) as proxy:
            try:
                reply = await _model(proxy.url).ainvoke("hi")
            finally:
                await http.aclose_clients()

            assert reply.content == "ok"
            assert proxy.targets == [f"{_BASE}/chat/completions"]
