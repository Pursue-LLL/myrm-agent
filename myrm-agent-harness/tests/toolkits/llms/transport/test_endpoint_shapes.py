"""The address a user pastes, and the request URL it becomes.

Every row states a shape people actually paste (an API root, a full operation URL, the Azure portal's *Target URI*,
a Google AI Studio OpenAI-compatibility base, ...) and the exact URL the request must reach. ``basis`` says what
makes the expectation right, so a reviewer can tell an authority from a design choice:

- ``sdk``      the OpenAI SDK's rule: ``base_url`` + operation path, a query is the client's ``default_query``;
- ``azure``    Microsoft Learn's Azure OpenAI URL forms (``/openai/deployments/{name}/...?api-version=``, the v1 route);
- ``google``   answered by the live Gemini API: ``/v1beta/models/{m}:generateContent`` is routed (403 without a key)
               while the same path under ``/v1beta/openai`` is 404, so the OpenAI-compatibility base is not a native root;
- ``frontend`` what the UI's former ``normalizeApiUrl`` produced for the same text (it ran before the harness did);
- ``design``   a choice with no external authority, kept explicit so it is not mistaken for a standard.
"""

from __future__ import annotations

from typing import NamedTuple
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

_MESSAGES = [{"role": "user", "content": "hi"}]
_GENERIC = "mystery/chat-1"
_AZURE_DEFAULT = "?api-version=2025-02-01-preview"
_GEMINI = "https://generativelanguage.googleapis.com"


class Shape(NamedTuple):
    name: str
    model: str
    pasted: str
    reaches: str
    basis: str


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


_OPENAI_COMPATIBLE = [
    Shape("root", _GENERIC, "https://host.example/v1", "https://host.example/v1/chat/completions", "sdk"),
    Shape("trailing slash", _GENERIC, "https://host.example/v1/", "https://host.example/v1/chat/completions", "sdk"),
    Shape("host only", _GENERIC, "https://host.example", "https://host.example/chat/completions", "sdk"),
    Shape(
        "port and prefix", _GENERIC, "http://10.0.0.5:8080/gw/v1", "http://10.0.0.5:8080/gw/v1/chat/completions", "sdk"
    ),
    Shape(
        "chat operation",
        _GENERIC,
        "https://host.example/v1/chat/completions",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "chat operation, slash",
        _GENERIC,
        "https://host.example/v1/chat/completions/",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "responses operation",
        _GENERIC,
        "https://host.example/zen/go/v1/responses",
        "https://host.example/zen/go/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "completions operation",
        _GENERIC,
        "https://host.example/v1/completions",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "models list",
        _GENERIC,
        "https://host.example/v1/models",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "embeddings operation",
        _GENERIC,
        "https://host.example/v1/embeddings",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "query is the default_query",
        _GENERIC,
        "https://host.example/v1?team=a&x=1",
        "https://host.example/v1/chat/completions?team=a&x=1",
        "sdk",
    ),
    Shape(
        "operation and query",
        _GENERIC,
        "https://host.example/v1/chat/completions?team=a",
        "https://host.example/v1/chat/completions?team=a",
        "sdk",
    ),
    Shape(
        "fragment is never sent",
        _GENERIC,
        "https://host.example/v1#section",
        "https://host.example/v1/chat/completions",
        "design",
    ),
    Shape(
        "credentials in the address are kept",
        _GENERIC,
        "https://u:p@host.example/v1",
        "https://u:p@host.example/v1/chat/completions",
        "design",
    ),
]

_AZURE = [
    Shape(
        "resource root",
        "azure/gpt-4o",
        "https://res.openai.azure.com",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{_AZURE_DEFAULT}",
        "azure",
    ),
    Shape(
        "resource root, slash",
        "azure/gpt-4o",
        "https://res.openai.azure.com/",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{_AZURE_DEFAULT}",
        "azure",
    ),
    Shape(
        "/openai prefix",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{_AZURE_DEFAULT}",
        "azure",
    ),
    Shape(
        "v1 route",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/v1/",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{_AZURE_DEFAULT}",
        "azure",
    ),
    Shape(
        "deployment root",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/deployments/gpt-4o",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{_AZURE_DEFAULT}",
        "azure",
    ),
    Shape(
        "portal Target URI",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21",
        "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21",
        "azure",
    ),
    Shape(
        "version only",
        "azure/gpt-4o",
        "https://res.openai.azure.com?api-version=2024-10-21",
        "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21",
        "azure",
    ),
    Shape(
        "the model field names the deployment",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/deployments/other/chat/completions",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{_AZURE_DEFAULT}",
        "design",
    ),
]

_GEMINI_NATIVE = [
    Shape(
        "official host only",
        "gemini/gemini-2.0-flash",
        _GEMINI,
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "official root",
        "gemini/gemini-2.0-flash",
        f"{_GEMINI}/v1beta/",
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "models list",
        "gemini/gemini-2.0-flash",
        f"{_GEMINI}/v1beta/models",
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "pasted generateContent URL",
        "gemini/gemini-2.0-flash",
        f"{_GEMINI}/v1beta/models/gemini-pro:generateContent",
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "pasted streaming URL",
        "gemini/gemini-2.0-flash",
        f"{_GEMINI}/v1beta/models/gemini-pro:streamGenerateContent",
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "OpenAI-compatibility base",
        "gemini/gemini-2.0-flash",
        f"{_GEMINI}/v1beta/openai/",
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "OpenAI-compatibility operation",
        "gemini/gemini-2.0-flash",
        f"{_GEMINI}/v1beta/openai/chat/completions",
        f"{_GEMINI}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "a relay's host is not guessed",
        "gemini/gemini-2.0-flash",
        "https://relay.example",
        "https://relay.example/models/gemini-2.0-flash:generateContent",
        "design",
    ),
    Shape(
        "a relay's versioned root",
        "gemini/gemini-2.0-flash",
        "https://relay.example/v1beta",
        "https://relay.example/v1beta/models/gemini-2.0-flash:generateContent",
        "design",
    ),
]

_NATIVE_WIRES = [
    Shape(
        "anthropic root",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape(
        "anthropic /v1",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com/v1",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape(
        "anthropic operation",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com/v1/messages",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape(
        "anthropic models list",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com/v1/models",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape("ollama root", "ollama/llama3", "http://localhost:11434", "http://localhost:11434/api/chat", "frontend"),
    Shape("ollama /v1", "ollama/llama3", "http://localhost:11434/v1", "http://localhost:11434/api/chat", "frontend"),
    Shape(
        "ollama OpenAI operation",
        "ollama/llama3",
        "http://localhost:11434/v1/chat/completions",
        "http://localhost:11434/api/chat",
        "frontend",
    ),
    Shape(
        "ollama native operation",
        "ollama/llama3",
        "http://localhost:11434/api/chat",
        "http://localhost:11434/api/chat",
        "frontend",
    ),
]


def _ids(shapes: list[Shape]) -> list[str]:
    return [f"{shape.basis}:{shape.name}" for shape in shapes]


class TestChatAddress:
    @pytest.mark.parametrize("shape", _OPENAI_COMPATIBLE, ids=_ids(_OPENAI_COMPATIBLE))
    def test_an_openai_compatible_endpoint(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    @pytest.mark.parametrize("shape", _AZURE, ids=_ids(_AZURE))
    def test_azure_openai(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    @pytest.mark.parametrize("shape", _GEMINI_NATIVE, ids=_ids(_GEMINI_NATIVE))
    def test_gemini_native(self, shape: Shape) -> None:
        assert _chat(shape.model, shape.pasted) == shape.reaches

    @pytest.mark.parametrize("shape", _NATIVE_WIRES, ids=_ids(_NATIVE_WIRES))
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
        route = resolve_route(_GENERIC, api_key="k", api_base="https://host.example/v1/responses?team=a")

        assert _wire(openai_responses.prepare(route, {"input": "hi"})) == "https://host.example/v1/responses?team=a"

    def test_embeddings_keep_the_pasted_query(self) -> None:
        route = service_route(
            "openai/text-embedding-3-small", api_key="k", api_base="https://host.example/v1/embeddings?team=a"
        )

        assert _wire(embeddings._openai_request(route, ["x"])) == "https://host.example/v1/embeddings?team=a"

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
            resolve_route(_GENERIC, api_key="k", api_base=pasted)

        assert not any(part in str(refused.value) for part in ("SECRET", "host.example", "11434", "::1"))

    def test_a_blank_address_is_no_address(self) -> None:
        assert resolve_route("openai/gpt-4o", api_key="k", api_base="   ").base_url == "https://api.openai.com/v1"
