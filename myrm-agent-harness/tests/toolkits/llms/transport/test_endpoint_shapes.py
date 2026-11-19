"""The address a user pastes, and the request URL it becomes.

The rows (``endpoint_shape_rows.py``) each state a shape people actually paste and the exact URL the request must
reach, with the ``basis`` that makes the expectation right. These tests run them through the real request builders.
"""

from __future__ import annotations

from urllib.parse import urlencode

import pytest

from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_messages,
    embeddings,
    gemini_generate,
    ollama_chat,
    openai_chat,
    openai_responses,
)
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError, resolve_route
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route

from .endpoint_shape_rows import (
    AZURE,
    GEMINI_NATIVE,
    GENERIC_MODEL,
    NATIVE_WIRES,
    OPENAI_COMPATIBLE,
    Shape,
)

_MESSAGES = [{"role": "user", "content": "hi"}]


def _wire(request: PreparedRequest) -> str:
    """The address a request goes to, query included."""
    return request.url + (f"?{urlencode(dict(request.query))}" if request.query else "")


def _chat(model: str, pasted: str, **params: object) -> str:
    route = resolve_route(model, api_key="k", api_base=pasted)
    prepare = {
        "openai_chat": openai_chat.prepare,
        "azure_openai": openai_chat.prepare,
        "gemini": gemini_generate.prepare,
        "anthropic": anthropic_messages.prepare,
        "ollama": ollama_chat.prepare,
    }[route.profile.wire]
    return _wire(prepare(route, _MESSAGES, params))


def _ids(shapes: list[Shape]) -> list[str]:
    return [f"{shape.basis}:{shape.name}" for shape in shapes]


class TestChatAddress:
    @pytest.mark.parametrize("shape", OPENAI_COMPATIBLE, ids=_ids(OPENAI_COMPATIBLE))
    def test_an_openai_compatible_endpoint(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    @pytest.mark.parametrize("shape", AZURE, ids=_ids(AZURE))
    def test_azure_openai(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    @pytest.mark.parametrize("shape", GEMINI_NATIVE, ids=_ids(GEMINI_NATIVE))
    def test_gemini_native(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    @pytest.mark.parametrize("shape", NATIVE_WIRES, ids=_ids(NATIVE_WIRES))
    def test_the_native_wires(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    def test_the_caller_chosen_api_version_beats_the_pasted_one(self) -> None:
        pasted = "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21"

        reaches = _chat("azure/gpt-4o", pasted, api_version="2025-04-01-preview")

        assert reaches.endswith("/chat/completions?api-version=2025-04-01-preview")

    def test_a_pasted_gemini_query_rides_along_with_the_stream_flag(self) -> None:
        reaches = _chat("gemini/gemini-2.0-flash", "https://relay.example/v1beta?team=a", stream=True)

        assert reaches == "https://relay.example/v1beta/models/gemini-2.0-flash:streamGenerateContent?team=a&alt=sse"


class TestOtherOperations:
    """The same address serves the Responses API and embeddings, so they must read it the same way."""

    def test_azure_responses_ignores_a_chat_api_version_and_the_deployment_path(self) -> None:
        pasted = "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21"
        route = resolve_route("azure/gpt-5.4", api_key="k", api_base=pasted)

        request = openai_responses.prepare(route, {"input": "hi"})

        assert _wire(request) == "https://res.openai.azure.com/openai/v1/responses?api-version=preview"

    def test_a_pasted_responses_url_serves_chat_and_responses_alike(self) -> None:
        route = resolve_route(GENERIC_MODEL, api_key="k", api_base="https://host.example/v1/responses?team=a")

        assert _wire(openai_responses.prepare(route, {"input": "hi"})) == "https://host.example/v1/responses?team=a"

    def test_embeddings_keep_the_pasted_query(self) -> None:
        route = service_route(
            "openai/text-embedding-3-small", api_key="k", api_base="https://host.example/v1/embeddings?team=a"
        )

        assert _wire(embeddings._openai_request(route, ["x"])) == "https://host.example/v1/embeddings?team=a"

    def test_ollama_embeddings_add_the_v1_path_and_keep_the_pasted_query(self) -> None:
        route = service_route("ollama/nomic-embed-text", api_key="k", api_base="http://host.example:11434?team=a")

        assert _wire(embeddings._openai_request(route, ["x"])) == "http://host.example:11434/v1/embeddings?team=a"

    def test_a_service_address_is_read_by_the_same_grammar(self) -> None:
        route = service_route(
            "openai/text-embedding-3-small", api_key="k", api_base="https://host.example/v1/embeddings/#frag"
        )

        assert route.base_url == "https://host.example/v1"


class TestAnAddressThatIsNotAUrl:
    @pytest.mark.parametrize(
        "pasted",
        [
            "host.example/v1?key=SECRET",
            "localhost:11434",
            "//host.example/v1",
            "ftp://host.example",
            "https://?key=SECRET",
            "https://[::1",
        ],
    )
    def test_it_is_refused_before_any_request_with_a_reason_that_hides_the_value(self, pasted: str) -> None:
        with pytest.raises(UnsupportedProviderError, match="absolute http:// or https:// URL") as refused:
            resolve_route(GENERIC_MODEL, api_key="k", api_base=pasted)

        assert not any(part in str(refused.value) for part in ("SECRET", "host.example", "11434", "::1"))

    def test_a_blank_address_is_no_address(self) -> None:
        assert resolve_route("openai/gpt-4o", api_key="k", api_base="   ").base_url == "https://api.openai.com/v1"
