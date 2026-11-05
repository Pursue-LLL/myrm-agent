"""检索（embedding / reranker）配置解析。

[POS]
channel_bridge 配置解析包的子模块；只服务 retrieval 配置。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.channel_bridge.config_parsers.common import _PROVIDER_API_BASES
from app.core.channel_bridge.model_resolver import _to_litellm_model

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig


def extract_retrieval_models(
    retrieval_dict: dict[str, object] | None,
) -> tuple["EmbeddingConfig | None", "RerankerConfig | None"]:
    """Extract EmbeddingConfig and RerankerConfig from the frontend's retrieval config.

    Only returns configs where applied=True and apiKey is present.
    Converts provider+model to LiteLLM format and fills in default API bases.
    """
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    if not retrieval_dict:
        return None, None

    embedding_cfg = _build_embedding_config(retrieval_dict, EmbeddingConfig)
    reranker_cfg = _build_reranker_config(retrieval_dict, RerankerConfig)
    return embedding_cfg, reranker_cfg


def _build_embedding_config(
    retrieval_dict: dict[str, object],
    cls: type["EmbeddingConfig"],
) -> "EmbeddingConfig | None":
    """Build EmbeddingConfig from retrieval dict."""
    params = _parse_retrieval_params(retrieval_dict, "embeddingConfig", "embeddingApplied")
    if not params:
        return None
    return cls(model=params[0], api_key=params[1], api_base=params[2])


def _build_reranker_config(
    retrieval_dict: dict[str, object],
    cls: type["RerankerConfig"],
) -> "RerankerConfig | None":
    """Build RerankerConfig from retrieval dict."""
    params = _parse_retrieval_params(retrieval_dict, "rerankerConfig", "rerankerApplied")
    if not params:
        return None
    return cls(model=params[0], api_key=params[1], api_base=params[2])


def _parse_retrieval_params(
    retrieval_dict: dict[str, object],
    config_key: str,
    applied_key: str,
) -> tuple[str, str, str | None] | None:
    """Parse model/api_key/api_base from a single retrieval sub-config.

    Returns (model, api_key, api_base) tuple, or None if not applied or incomplete.
    """
    if not retrieval_dict.get(applied_key):
        return None

    raw = retrieval_dict.get(config_key)
    if not isinstance(raw, dict):
        return None

    api_key = raw.get("apiKey")
    if not api_key or not isinstance(api_key, str):
        return None

    provider = str(raw.get("provider", ""))
    model = str(raw.get("model", ""))
    if not model:
        return None

    litellm_model = _to_litellm_model(provider, model)
    api_base = str(raw.get("apiBase") or _PROVIDER_API_BASES.get(provider, "")) or None
    return litellm_model, api_key, api_base
