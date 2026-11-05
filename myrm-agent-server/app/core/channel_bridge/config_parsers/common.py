"""通用解析：数值兜底、检索模型、模型配置辅助与视频能力推断。

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.channel_bridge.model_resolver import _to_litellm_model

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


def _int_setting(val: object, default: int) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val, 10)
        except ValueError:
            return default
    return default


def _float_setting(val: object, default: float) -> float:
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return default
    return default


_PROVIDER_API_BASES: dict[str, str] = {
    "siliconflow": "https://api.siliconflow.cn/v1",
}


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


def _model_config_identity(cfg: "ModelConfig") -> tuple[str, str | None]:
    return (cfg.model, cfg.base_url)


def _append_unique_model_config(
    configs: list["ModelConfig"],
    seen: set[tuple[str, str | None]],
    cfg: "ModelConfig | None",
) -> None:
    if cfg is None:
        return
    key = _model_config_identity(cfg)
    if key in seen:
        return
    seen.add(key)
    configs.append(cfg)


def _build_enriched_model_config(
    *,
    provider_id: str,
    model: str,
    provider: dict[str, object],
    providers_dict: dict[str, object] | None,
    selection_supports_vision: bool | None = None,
    infer_video: bool = False,
) -> "ModelConfig | None":
    """Build ModelConfig with wire enrich + capabilities + context window."""
    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )
    from app.core.types import ModelConfig
    from app.core.wire.enrich import enrich_model_config

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    ptype = str(provider.get("providerType", "")) or None
    full_model = _to_litellm_model(provider_id, model, ptype)
    oauth_base = provider.get("_oauthBaseUrl")
    api_url_raw = oauth_base if oauth_base else provider.get("apiUrl") or provider.get("baseURL") or ""
    api_url = str(api_url_raw).strip() or None
    egress_proxy_raw = provider.get("egressProxy") or provider.get("egress_proxy")
    egress_proxy = str(egress_proxy_raw).strip() or None if egress_proxy_raw else None

    cfg = enrich_model_config(
        ModelConfig(
            model=full_model,
            api_key=api_key,
            base_url=api_url,
            egress_proxy=egress_proxy,
        ),
        provider_id=provider_id,
    )
    if providers_dict is not None:
        cfg = enrich_model_capabilities(
            cfg,
            providers_dict,
            selection_supports_vision=selection_supports_vision,
        )
        cfg = enrich_model_context_window(cfg, providers_dict)
    if infer_video:
        cfg = cfg.model_copy(update={"supports_video": _infer_supports_video(cfg.model, providers_dict)})
    return cfg


def _infer_supports_video(
    model: str,
    providers_dict: dict[str, object] | None,
) -> bool:
    """Infer native video support from custom model info or model id."""
    from app.core.channel_bridge.model_resolver import _lookup_custom_model_info

    custom = _lookup_custom_model_info(model, providers_dict)
    if custom is not None:
        if "supports_video" in custom:
            return bool(custom["supports_video"])
        if "supports_video_input" in custom:
            return bool(custom["supports_video_input"])
    return False


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


def _extract_active_key(provider: dict[str, object]) -> str | None:
    """Extract active API key from provider dict."""
    if not provider:
        return None

    # Try direct apiKey first
    api_key = provider.get("apiKey")
    if api_key and isinstance(api_key, str):
        return api_key

    # Try keys array
    keys = provider.get("keys")
    if isinstance(keys, list) and len(keys) > 0:
        # Find active key or first key
        active_key = next((k for k in keys if isinstance(k, dict) and k.get("isActive")), keys[0])
        if isinstance(active_key, dict):
            key_val = active_key.get("key")
            if isinstance(key_val, str) and key_val:
                return key_val

    return None
