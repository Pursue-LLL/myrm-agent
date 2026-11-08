"""Records the outbound HTTP requests and decoded results of the embedding, rerank, image and search entry points.

[INPUT]
- golden_recorder (POS: httpx request recorder shared by every golden matrix)
- golden_service_answers::Answerer (POS: canned provider answers)
- retriever.embedding.cloud_embedding::CloudEmbedding, retriever.reranker.cloud_reranker::CloudReranker (POS: entries)
- llms.image.generator::ImageGenerator, web_search.providers.search_service_factory::build_search_service (POS: entries)

[OUTPUT]
- capture_services: {"family/provider|base|scenario": {"requests": [...], "result": ..., "error": str}} for the matrix
- ``python -m tests.toolkits.llms.transport.golden_services OUT.json``: records the matrix into a file

[POS]
Library-agnostic capture of the four service paths, through the same public classes the product calls. The committed
``golden_services_baseline.json`` was recorded by running this module against the previous client library (litellm
1.97.0) at commit b218e6f1d7; the golden test replays the matrix on the transport and diffs requests and results.
Nothing here imports the client library, so the same module runs against either stack.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from pydantic import SecretStr

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.llms.image.generator import ImageGenerationConfig, ImageGenerator
from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import CloudEmbedding
from myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker import CloudReranker
from myrm_agent_harness.toolkits.web_search.providers.search_service_factory import build_search_service
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig, _provider_default_params

from .golden_recorder import Case, install_request_recorder
from .golden_service_answers import PNG_B64, Answerer

_KEY = "sk-golden-test-key"
_BASE = "http://golden.invalid/v1"
_GATEWAY = ToolGatewayConfig(use_gateway=True, gateway_url="http://gateway.invalid/relay", auth_token="gw-token")
_PNG = base64.b64decode(PNG_B64)

_BOTH, _CUSTOM = (False, True), (True,)

# family entry -> (model as the settings layer builds it, base variants)
EMBEDDING: dict[str, tuple[str, tuple[bool, ...]]] = {
    "openai": ("openai/text-embedding-3-small", _BOTH),
    "openai_bare": ("text-embedding-3-small", _BOTH),
    "azure": ("azure/text-embedding-3-small", _CUSTOM),
    "cohere": ("cohere/embed-english-v3.0", _BOTH),
    "voyage": ("voyage/voyage-3", _BOTH),
    "jina_ai": ("jina_ai/jina-embeddings-v3", _BOTH),
    "mistral": ("mistral/mistral-embed", _BOTH),
    "gemini": ("gemini/text-embedding-004", _BOTH),
    "together_ai": ("together_ai/BAAI/bge-large-en-v1.5", _BOTH),
    "ollama": ("ollama/nomic-embed-text", _BOTH),
    "lm_studio": ("lm_studio/nomic-embed-text", _BOTH),
    "openrouter": ("openrouter/openai/text-embedding-3-small", _BOTH),
    "siliconflow": ("BAAI/bge-m3", _CUSTOM),
}
EMBEDDING_SCENARIOS = ("single", "batch")
RERANK: dict[str, tuple[str, tuple[bool, ...]]] = {
    "cohere": ("cohere/rerank-v3.5", _BOTH),
    "jina_ai": ("jina_ai/jina-reranker-v2-base-multilingual", _BOTH),
    "voyage": ("voyage/rerank-2", _BOTH),
    "together_ai": ("together_ai/Salesforce/Llama-Rank-V1", _BOTH),
    "azure_ai": ("azure_ai/cohere-rerank-v3.5", _CUSTOM),
    "openai_compat": ("openai/BAAI/bge-reranker-v2-m3", _CUSTOM),
}
RERANK_SCENARIOS = ("top_k", "all")
IMAGE: dict[str, tuple[str, tuple[bool, ...]]] = {
    "dall_e_3": ("dall-e-3", _BOTH),
    "dall_e_2": ("dall-e-2", _BOTH),
    "gpt_image_1": ("gpt-image-1", _BOTH),
    "openai_gpt_image": ("openai/gpt-image-1", _BOTH),
    "gemini_imagen": ("gemini/imagen-3.0-generate-002", _BOTH),
    "stability": ("stability/stable-diffusion-xl", _BOTH),
    "xai": ("xai/grok-imagine-image", _BOTH),
    "flux": ("flux/schnell", _BOTH),
    "together_flux": ("together_ai/black-forest-labs/FLUX.1-schnell", _BOTH),
    "minimax": ("minimax_image/image-01", _BOTH),
    "azure": ("azure/dall-e-3", _CUSTOM),
    "openai_compat": ("openai/some-image-model", _CUSTOM),
}
IMAGE_SCENARIOS = ("generate", "generate_many", "edit", "edit_mask", "gateway", "bad_key", "server_error")
SEARCH: dict[str, tuple[bool, ...]] = {
    "perplexity": _BOTH,
    "tavily": _BOTH,
    "exa_ai": _BOTH,
    "parallel_ai": _BOTH,
    "google_pse": _BOTH,
    "dataforseo": _BOTH,
    "firecrawl": _BOTH,
    "searxng": _CUSTOM,
    "brave": _BOTH,
    "serper": _BOTH,
}
SEARCH_SCENARIOS = ("basic", "filters", "provider_params", "product_defaults", "gateway", "bad_key")
_SEARCH_KEY = {"dataforseo": "golden-login:golden-password"}  # the one provider whose key is a login pair
_ENGINE_ID = "cx-golden"  # Google PSE addresses a search engine besides authenticating
_PROVIDER_PARAMS: dict[str, dict[str, object]] = {
    "perplexity": {"max_tokens_per_page": 512},
    "tavily": {"topic": "news", "search_depth": "advanced", "include_answer": True},
    "exa_ai": {"contents": {"highlights": True}},
    "parallel_ai": {"mode": "basic"},
    "google_pse": {"search_engine_id": _ENGINE_ID},
    "dataforseo": {"language_code": "en"},
    "firecrawl": {"sources": ["web", "news"], "tbs": "qdr:m"},
    "searxng": {"engines": "google,bing", "language": "en", "pageno": 2, "time_range": "month"},
    "brave": {"freshness": "pw"},
    "serper": {"gl": "us"},
}


def _failure(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    return "ImageGenerationError" if type(exc).__name__ == "ImageGenerationError" else f"failed:{status}"


async def _embedding(model: str, with_base: bool, scenario: str, answer: Answerer) -> object:
    service = CloudEmbedding(model=model, api_key=_KEY, api_base=_BASE if with_base else None, max_retries=0)
    if scenario == "single":
        return [await service.embed("hello")]
    return await service.embed_batch(["alpha", "", "gamma"])


async def _rerank(model: str, with_base: bool, scenario: str, answer: Answerer) -> object:
    service = CloudReranker(model=model, api_key=_KEY, api_base=_BASE if with_base else None)
    found = await service.rerank("what is ai", ["d0", "d1", "d2"], top_k=2 if scenario == "top_k" else None)
    return [[item.index, item.score, item.text] for item in found]


async def _image(model: str, with_base: bool, scenario: str, answer: Answerer) -> object:
    config = ImageGenerationConfig(
        model=model,
        api_key=SecretStr(_KEY),
        base_url=_BASE if with_base else None,
        timeout_seconds=30,
        max_retries=1 if scenario == "server_error" else 0,
        gateway_config=_GATEWAY if scenario == "gateway" else None,
    )
    generator = ImageGenerator(config)
    if scenario == "bad_key":
        answer.status = 401
    elif scenario == "server_error":
        answer.status = 500
    if scenario.startswith("edit"):
        result = await generator.edit(_PNG, "make it blue", mask=_PNG if scenario == "edit_mask" else None)
    elif scenario == "generate_many":
        result = await generator.generate("a cat", size="1024x1024", quality="hd", style="vivid", n=2)
    else:
        result = await generator.generate("a cat")
    return {
        "model": result.model,
        "url": result.url,
        "b64_json": result.b64_json,
        "revised_prompt": result.revised_prompt,
        "mime_type": result.mime_type,
        "attempts": len(result.attempts),
    }


async def _search(provider: str, with_base: bool, scenario: str, answer: Answerer) -> object:
    config = SearchServiceConfig(
        search_service=provider,
        api_key=_SEARCH_KEY.get(provider, _KEY),
        api_base=_BASE if with_base else None,
        gateway_config=_GATEWAY if scenario == "gateway" and provider != "searxng" else None,
    )
    params: dict[str, object] = {}
    if scenario == "filters":
        params = {"search_domain_filter": ["example.com"], "country": "us"}
    elif scenario == "provider_params":
        params = dict(_PROVIDER_PARAMS.get(provider, {}))
    elif scenario == "product_defaults":
        params = _provider_default_params(provider)
    elif scenario == "bad_key":
        answer.status = 401
    if provider == "google_pse":
        params.setdefault("search_engine_id", _ENGINE_ID)
    rows = await build_search_service(config).search("golden query", 5, **params)
    return [r.model_dump(include={"title", "link", "snippet", "summary", "date"}) for r in rows]


_RUNNERS: dict[str, Callable[[str, bool, str, Answerer], Awaitable[object]]] = {
    "embedding": _embedding,
    "rerank": _rerank,
    "image": _image,
    "search": _search,
}


def case_keys() -> list[tuple[str, str, bool, str, str]]:
    """(family, provider key, with_base, scenario, model-or-provider) of every case in matrix order."""
    keys: list[tuple[str, str, bool, str, str]] = []
    for family, table, scenarios in (
        ("embedding", EMBEDDING, EMBEDDING_SCENARIOS),
        ("rerank", RERANK, RERANK_SCENARIOS),
        ("image", IMAGE, IMAGE_SCENARIOS),
    ):
        for provider, (model, bases) in table.items():
            keys.extend((family, provider, base, scenario, model) for base in bases for scenario in scenarios)
    keys.extend(
        ("search", provider, base, scenario, provider)
        for provider, bases in SEARCH.items()
        for base in bases
        for scenario in SEARCH_SCENARIOS
    )
    return keys


def case_name(family: str, provider: str, with_base: bool, scenario: str) -> str:
    return f"{family}/{provider}|{'custom_base' if with_base else 'default_base'}|{scenario}"


def capture_services(monkeypatch: pytest.MonkeyPatch, families: frozenset[str] | None = None) -> dict[str, Case]:
    """Run the matrix on the installed stack; sleeping between retries is skipped so the run stays short."""
    answer = Answerer()
    sink = install_request_recorder(monkeypatch, answer)
    # the previous client library read the Google PSE engine and key only from the environment
    monkeypatch.setenv("GOOGLE_PSE_ENGINE_ID", _ENGINE_ID)
    monkeypatch.setenv("GOOGLE_PSE_API_KEY", _KEY)
    real_sleep = asyncio.sleep

    async def no_wait(delay: float, *args: object, **kwargs: object) -> None:
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    async def main() -> dict[str, Case]:
        cases: dict[str, Case] = {}
        for family, provider, with_base, scenario, model in case_keys():
            if families is not None and family not in families:
                continue
            sink.clear()
            answer.status = 200
            result: object = None
            error = ""
            try:
                result = await _RUNNERS[family](model, with_base, scenario, answer)
            except Exception as exc:  # the request is already recorded; the failure kind is part of the case
                error = _failure(exc)
            cases[case_name(family, provider, with_base, scenario)] = {
                "requests": list(sink),
                "result": result,
                "error": error,
            }
        return cases

    return asyncio.run(main())


def _record_to(path: Path, meta: dict[str, str]) -> None:
    with pytest.MonkeyPatch.context() as patch:
        cases = capture_services(patch)
    document: dict[str, object] = {"_meta": meta, **cases}
    path.write_text(json.dumps(document, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # OUT.json [key=value ...]: the key=value pairs describe the stack being recorded and land in ``_meta``
    _record_to(Path(sys.argv[1]), dict(arg.split("=", 1) for arg in sys.argv[2:]))
