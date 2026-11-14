"""Records which endpoint each provider's chat, embedding, rerank and image calls reach for each shape of base URL.

[INPUT]
- golden_matrix::PROVIDERS (POS: the model id and factory options of every chat provider)
- golden_services::capture_services (POS: the embedding, rerank and image entry points, driven through a base URL)
- golden_recorder::install_request_recorder (POS: observes the final HTTP request)

[OUTPUT]
- capture_shapes: {"family/provider|scenario|shape": [where each request went]} for the whole matrix
- ``python -m tests.toolkits.llms.transport.golden_shapes OUT.json``: records the matrix into a file

[POS]
The other golden matrices save every custom base URL as ``<host>/v1``. A settings screen lets people save anything:
a bare host, a trailing slash, a gateway prefix, the pasted URL of one operation. This matrix replays each of those
and keeps only the path and query a request reached (the host only when it is not the probe's own), because that is
all a mistyped base URL can move. The committed ``golden_shapes_baseline.json`` was recorded by running this module
against the baseline client library (litellm 1.97.0, the version the server pinned) at commit dc1b5711db, where the chat
factory was named ``create_litellm_model``; the recording harness aliased it to the name used here, so nothing in
this module depends on either library.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model

from . import golden_services
from .golden_allowed_types import HIDDEN_FETCHES
from .golden_matrix import PROVIDERS
from .golden_recorder import Record, install_request_recorder

_HOST = "shape.invalid"
_CHAT_PROVIDERS = (
    "openai",
    "azure",
    "anthropic",
    "gemini",
    "ollama",
    "deepseek",
    "openrouter",
    "zai",
    "xai",
    "moonshot",
    "lm_studio",
    "mistral",
    "together_ai",
    "volcengine",
    "fireworks_ai",
    "minimax",
    "groq",
    "dashscope",
    "perplexity",
    "cohere_chat",
    "cerebras",
    "xiaomi_mimo",
    "yunshu",
)
CHAT_SHAPES = (
    ("bare", ""),
    ("slash", "/"),
    ("v1", "/v1"),
    ("v1slash", "/v1/"),
    ("gw_v1", "/gw/v1"),
    ("gw", "/gw"),
    ("full_chat", "/v1/chat/completions"),
    ("full_chat_gw", "/gw/v1/chat/completions"),
    ("full_messages", "/v1/messages"),
    ("api", "/api"),
    ("api_chat", "/api/chat"),
    ("v1beta", "/v1beta"),
)
SERVICE_SHAPES = (
    ("bare", ""),
    ("slash", "/"),
    ("v1", "/v1"),
    ("v1slash", "/v1/"),
    ("gw_v1", "/gw/v1"),
    ("gw", "/gw"),
    ("full_op", "/v1/OPERATION"),
)
_OPERATION = {"embedding": "embeddings", "rerank": "rerank", "image": "images/generations"}
_SERVICE_SCENARIOS = frozenset({"single", "top_k", "generate", "edit"})


def _refuse(request: httpx.Request) -> httpx.Response:
    """A 400, which no client retries, so each case reaches the wire once."""
    body = {"error": {"message": "shape probe", "type": "invalid_request_error"}}
    return httpx.Response(400, json=body, request=request)


def _where(record: Record) -> str:
    """Path and query of a request, led by its host only when that is not the probe's own."""
    parts = urlsplit(str(record["url"]))
    host = "" if parts.netloc == _HOST else parts.netloc
    query = f"?{record['query']}" if record["query"] else ""
    return f"{host}{parts.path}{query}"


def _visible(sink: list[Record]) -> list[Record]:
    return [r for r in sink if not any(hidden in str(r["url"]) for hidden in HIDDEN_FETCHES)]


async def _chat_shapes(sink: list[Record]) -> dict[str, list[str]]:
    cases: dict[str, list[str]] = {}
    for provider in _CHAT_PROVIDERS:
        model, extra = PROVIDERS[provider]
        for shape, suffix in CHAT_SHAPES:
            sink.clear()
            with contextlib.suppress(Exception):  # the provider's refusal is the point: only where it went matters
                llm = create_chat_model(
                    model, api_key="sk-shape-test-key", streaming=False, base_url=f"http://{_HOST}{suffix}", **extra
                )
                await llm.ainvoke("hi")
            cases[f"chat/{provider}|basic|{shape}"] = sorted({_where(r) for r in _visible(sink)})
    return cases


def _service_shapes() -> dict[str, list[str]]:
    cases: dict[str, list[str]] = {}
    for shape, suffix in SERVICE_SHAPES:
        for family, operation in _OPERATION.items():
            base = f"http://{_HOST}{suffix.replace('OPERATION', operation)}"
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(golden_services, "_BASE", base)
                captured = golden_services.capture_services(patch, families=frozenset({family}))
            for name, case in captured.items():
                provider, base_kind, scenario = name.split("|")
                if base_kind == "custom_base" and scenario in _SERVICE_SCENARIOS:
                    requests = case["requests"]
                    assert isinstance(requests, list)
                    cases[f"{provider}|{scenario}|{shape}"] = [_where(r) for r in _visible(requests)]
    return cases


def capture_shapes() -> dict[str, list[str]]:
    """Run the matrix on the installed stack."""
    with pytest.MonkeyPatch.context() as patch:
        sink = install_request_recorder(patch, _refuse)
        chat = asyncio.run(_chat_shapes(sink))
    return {**chat, **_service_shapes()}


def _record_to(path: Path, meta: Mapping[str, str]) -> None:
    document: dict[str, object] = {"_meta": dict(meta), **capture_shapes()}
    path.write_text(json.dumps(document, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # OUT.json [key=value ...]: the key=value pairs describe the stack being recorded and land in ``_meta``
    _record_to(Path(sys.argv[1]), dict(arg.split("=", 1) for arg in sys.argv[2:]))
