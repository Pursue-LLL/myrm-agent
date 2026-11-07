"""CloudEmbedding sends each provider only the request parameters its embeddings API accepts.

Voyage's API takes `encoding_format` as null or "base64" and answers HTTP 400 to "float", while the OpenAI-style
providers (OpenAI, OpenAI-compatible endpoints such as SiliconFlow) and the providers LiteLLM maps the parameter for
(Cohere) are sent `float`. The wire body LiteLLM builds from these parameters is asserted in the server suite
(`tests/api/integrations/test_embedding_provider_wire_contract.py`).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import CloudEmbedding

_API_KEY = "sk-test"


async def _litellm_kwargs(model: str, api_base: str | None = None) -> dict[str, object]:
    """The keyword arguments CloudEmbedding hands to `litellm.aembedding` for one text."""
    seen: list[dict[str, object]] = []

    async def record(**kwargs: object) -> SimpleNamespace:
        seen.append(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.1] * 4}])

    with patch("litellm.aembedding", side_effect=record):
        await CloudEmbedding(model=model, api_key=_API_KEY, api_base=api_base).embed("hello")

    [kwargs] = seen
    return kwargs


@pytest.mark.parametrize("model", ["voyage/voyage-4-lite", "voyage/voyage-3"])
async def test_voyage_is_not_sent_an_encoding_format(model: str) -> None:
    assert await _litellm_kwargs(model) == {"model": model, "input": ["hello"], "api_key": _API_KEY}


@pytest.mark.parametrize(
    ("model", "api_base"),
    [
        ("openai/BAAI/bge-m3", "https://api.siliconflow.cn/v1"),
        ("BAAI/bge-m3", "https://api.siliconflow.cn/v1"),
        ("text-embedding-3-small", None),
        ("cohere/embed-multilingual-v3.0", None),
        ("jina_ai/jina-embeddings-v3", None),
    ],
)
async def test_other_providers_are_sent_float(model: str, api_base: str | None) -> None:
    kwargs = await _litellm_kwargs(model, api_base)

    assert kwargs["encoding_format"] == "float"


async def test_a_voyage_model_behind_a_custom_endpoint_is_an_openai_compatible_request() -> None:
    # A custom api_base makes CloudEmbedding address the endpoint as OpenAI-compatible, whatever the model's prefix.
    kwargs = await _litellm_kwargs("voyage/voyage-3", "https://gateway.example/v1")

    assert kwargs["model"] == "openai/voyage/voyage-3"
    assert kwargs["encoding_format"] == "float"
