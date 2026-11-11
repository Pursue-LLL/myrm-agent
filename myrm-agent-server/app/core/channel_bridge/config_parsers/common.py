"""[INPUT]
- app.core.channel_bridge.model_resolver::_extract_active_key / _to_route_model_id (POS: Aggregate exit of the model resolver package; import path unchanged.)

[OUTPUT]
- _int_setting: _int_setting
- _float_setting: _float_setting
- _model_config_identity: _model_config_identity
- _append_unique_model_config: _append_unique_model_config
- _build_enriched_model_config: Build ModelConfig with wire enrich + capabilities + context window.
- _infer_supports_video: Infer native video support from custom model info or model id.

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.channel_bridge.model_resolver import _extract_active_key, _to_route_model_id

if TYPE_CHECKING:
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
    full_model = _to_route_model_id(provider_id, model, ptype)
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
