"""Marketplace - 技能市场、镜像注册表与自定义源子域。

[POS]
聚合出口：
- market_service: 业务层技能市场服务（GitHub 源分析、SSE 进度、镜像懒加载）
- clawhub_registry: ClawHub 镜像 URL 持久化/apply（CLAWHUB_URL SSOT）
- clawhub_probe: ClawHub registry 连通性探测（薄封装 harness）
- custom_source_config: 自定义技能源持久化管理（.well-known/skills）
"""

from .clawhub_probe import probe_clawhub_registry, probe_configured_cn_mirror
from .clawhub_registry import (
    apply_clawhub_registry_url,
    get_registry_presets,
    normalize_clawhub_registry_url,
)
from .custom_source_config import (
    CustomSourceConfig,
    CustomSourceEntry,
    add_custom_source,
    load_custom_sources,
    remove_custom_source,
    save_custom_sources,
)
from .market_service import SkillMarketService, market_service

__all__ = [
    "SkillMarketService",
    "CustomSourceConfig",
    "CustomSourceEntry",
    "add_custom_source",
    "apply_clawhub_registry_url",
    "get_registry_presets",
    "load_custom_sources",
    "market_service",
    "normalize_clawhub_registry_url",
    "probe_clawhub_registry",
    "probe_configured_cn_mirror",
    "remove_custom_source",
    "save_custom_sources",
]
