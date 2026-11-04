"""GET /integrations/ollama/chat-model and the Ollama probe behind it.

[POS]
tests/api/integrations/test_ollama_chat_model.py

[INPUT]
- app.api.integrations.ollama: the tags reader, the capability-aware model pick, and the router, whose Ollama HTTP
  client is swapped for a mock transport

[OUTPUT]
- Pins that only a local model able to chat and call tools is offered, that an unknown capability is never guessed,
  and that the probed daemon URL is reported with the pick
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.integrations.ollama import (
    OllamaModel,
    find_chat_model,
    list_ollama_models,
)
from app.api.integrations.ollama import (
    router as ollama_router,
)
from app.config.deploy_mode import DeployMode

_BASE_URL = "http://ollama.test"
_CHAT = ["completion", "tools"]

app = FastAPI()
app.include_router(ollama_router, prefix="/api/v1/integrations/ollama")


def _tags(*entries: object) -> httpx.Response:
    return httpx.Response(200, json={"models": list(entries)})


def _show(capabilities: list[str] | None) -> httpx.Response:
    return httpx.Response(200, json={} if capabilities is None else {"capabilities": capabilities})


def _daemon(models: list[object], capabilities: dict[str, list[str] | None]) -> Callable[[httpx.Request], httpx.Response]:
    """A fake daemon: /api/tags lists `models`, /api/show answers from `capabilities` keyed by model name."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return _tags(*models)
        body = request.content.decode()
        for model_name, caps in capabilities.items():
            if f'"{model_name}"' in body:
                return _show(caps)
        return httpx.Response(404)

    return handler


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestListOllamaModels:
    @pytest.mark.asyncio
    async def test_unreachable_daemon_is_none(self) -> None:
        def refuse(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        async with _client(refuse) as client:
            assert await list_ollama_models(client, _BASE_URL) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(500),
            httpx.Response(200, content=b"not json"),
            httpx.Response(200, json=["not", "an", "object"]),
            httpx.Response(200, json={"models": None}),
        ],
        ids=["server-error", "not-json", "not-an-object", "models-null"],
    )
    async def test_an_answer_without_a_model_list_is_none(self, response: httpx.Response) -> None:
        async with _client(lambda _request: response) as client:
            assert await list_ollama_models(client, _BASE_URL) is None

    @pytest.mark.asyncio
    async def test_models_keep_the_daemons_order_and_flag_cloud_routed_ones(self) -> None:
        handler = _daemon(
            [
                {"name": "qwen3:8b"},
                {"name": "gpt-oss:120b-cloud", "remote_host": "https://ollama.com:443"},
                {"name": "llama3.2", "remote_model": "llama3.2"},
                {"no_name": True},
                "not-an-object",
            ],
            {},
        )
        async with _client(handler) as client:
            assert await list_ollama_models(client, _BASE_URL) == [
                OllamaModel(name="qwen3:8b", is_remote=False),
                OllamaModel(name="gpt-oss:120b-cloud", is_remote=True),
                OllamaModel(name="llama3.2", is_remote=True),
            ]

    @pytest.mark.asyncio
    async def test_an_empty_daemon_is_reachable_with_no_models(self) -> None:
        async with _client(_daemon([], {})) as client:
            assert await list_ollama_models(client, _BASE_URL) == []


class TestFindChatModel:
    @staticmethod
    def _models(*names: str) -> list[OllamaModel]:
        return [OllamaModel(name=name, is_remote=False) for name in names]

    @pytest.mark.asyncio
    async def test_returns_the_first_model_that_chats_and_calls_tools(self) -> None:
        handler = _daemon([], {"nomic-embed-text": ["embedding"], "qwen3:8b": _CHAT, "llama3.2": _CHAT})
        async with _client(handler) as client:
            picked = await find_chat_model(client, _BASE_URL, self._models("nomic-embed-text", "qwen3:8b", "llama3.2"))
        assert picked == "qwen3:8b"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "capabilities",
        [["completion"], ["completion", "vision"], ["tools"], ["embedding"], [], None],
        ids=["no-tools", "no-tools-vision", "no-completion", "embedding-only", "empty", "field-missing"],
    )
    async def test_a_model_without_both_capabilities_is_never_picked(self, capabilities: list[str] | None) -> None:
        async with _client(_daemon([], {"m": capabilities})) as client:
            assert await find_chat_model(client, _BASE_URL, self._models("m")) is None

    @pytest.mark.asyncio
    async def test_cloud_routed_models_are_not_probed_or_picked(self) -> None:
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.path)
            return _show(_CHAT)

        models = [OllamaModel(name="gpt-oss:120b-cloud", is_remote=True)]
        async with _client(handler) as client:
            assert await find_chat_model(client, _BASE_URL, models) is None
        assert asked == []

    @pytest.mark.asyncio
    async def test_a_failing_show_moves_on_to_the_next_model(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if b'"broken"' in request.content:
                return httpx.Response(500)
            if b'"garbled"' in request.content:
                return httpx.Response(200, content=b"not json")
            return _show(_CHAT)

        async with _client(handler) as client:
            picked = await find_chat_model(client, _BASE_URL, self._models("broken", "garbled", "good"))
        assert picked == "good"

    @pytest.mark.asyncio
    async def test_an_unreachable_daemon_mid_probe_yields_no_pick(self) -> None:
        def refuse(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        async with _client(refuse) as client:
            assert await find_chat_model(client, _BASE_URL, self._models("a", "b")) is None

    @pytest.mark.asyncio
    async def test_stops_at_the_first_match(self) -> None:
        asked: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(request.content)
            return _show(_CHAT)

        async with _client(handler) as client:
            await find_chat_model(client, _BASE_URL, self._models("a", "b", "c"))
        assert len(asked) == 1

    @pytest.mark.asyncio
    async def test_only_the_first_five_models_are_checked(self) -> None:
        asked: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(request.content)
            return _show(["embedding"])

        names = [f"m{i}" for i in range(8)]
        async with _client(handler) as client:
            assert await find_chat_model(client, _BASE_URL, self._models(*names)) is None
        assert len(asked) == 5


def _serve(handler: Callable[[httpx.Request], httpx.Response]) -> AbstractContextManager[object]:
    """Route the endpoint's Ollama calls to `handler`; the test client keeps the real transport."""
    real_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    return patch("app.api.integrations.ollama.httpx.AsyncClient", side_effect=factory)


async def _get_chat_model() -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.get("/api/v1/integrations/ollama/chat-model")


class TestChatModelEndpoint:
    @pytest.mark.asyncio
    async def test_sandbox_mode_is_refused(self) -> None:
        with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.SANDBOX):
            response = await _get_chat_model()
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reports_the_pick_with_the_daemon_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.delenv("OLLAMA_HOST_URL", raising=False)
        handler = _daemon(
            [{"name": "nomic-embed-text"}, {"name": "qwen3:8b"}], {"nomic-embed-text": ["embedding"], "qwen3:8b": _CHAT}
        )
        with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL), _serve(handler):
            response = await _get_chat_model()

        assert response.status_code == 200
        assert response.json()["data"] == {"model": "qwen3:8b", "base_url": "http://localhost:11434"}

    @pytest.mark.asyncio
    async def test_probes_and_reports_the_configured_daemon(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
        hosts: list[str] = []
        inner = _daemon([{"name": "qwen3:8b"}], {"qwen3:8b": _CHAT})

        def handler(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            return inner(request)

        with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL), _serve(handler):
            response = await _get_chat_model()

        assert response.json()["data"] == {"model": "qwen3:8b", "base_url": "http://host.docker.internal:11434"}
        assert set(hosts) == {"host.docker.internal"}

    @pytest.mark.asyncio
    async def test_a_stopped_daemon_offers_no_model(self) -> None:
        def refuse(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL), _serve(refuse):
            response = await _get_chat_model()

        assert response.status_code == 200
        assert response.json()["data"]["model"] is None

    @pytest.mark.asyncio
    async def test_a_daemon_with_only_an_embedding_model_offers_no_model(self) -> None:
        handler = _daemon([{"name": "nomic-embed-text"}], {"nomic-embed-text": ["embedding"]})
        with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL), _serve(handler):
            response = await _get_chat_model()

        assert response.json()["data"]["model"] is None

    @pytest.mark.asyncio
    async def test_an_empty_daemon_is_not_asked_about_capabilities(self) -> None:
        paths: list[str] = []
        inner = _daemon([], {})

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return inner(request)

        with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL), _serve(handler):
            response = await _get_chat_model()

        assert response.json()["data"]["model"] is None
        assert paths == ["/api/tags"]
