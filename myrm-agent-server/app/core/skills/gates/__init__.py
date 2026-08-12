"""Gates - 集成技能可用性、权限、隔离与依赖 gate 子域。

[POS]
聚合出口：
- oauth_availability: Integration 凭证 gate（OAuth / xAI provider / skill env / CLI bins）
- x_live_search_skill_enable: xAI provider 保存后 auto-enable prebuilt skill
- disabled_skill_roots: 未启用技能 storage 根目录注入 runtime context
- dependency_guard: 技能依赖影响面查询（pending 审核 / disable / uninstall 校验）
- permission_logger: 技能权限使用日志
"""

from .dependency_guard import get_dependents_for_skill, get_dependents_map
from .disabled_skill_roots import collect_disabled_skill_roots
from .oauth_availability import (
    GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    GOOGLE_WORKSPACE_SKILL_ID,
    LINEAR_PROJECT_SKILL_ID,
    NOTION_WORKSPACE_SKILL_ID,
    X_LIVE_SEARCH_SKILL_ID,
    X_LIVE_SEARCH_UNAVAILABLE,
    XURL_BIN_UNAVAILABLE,
    XURL_SKILL_ID,
    IntegrationOAuthSkillBackend,
    apply_integration_oauth_availability,
    apply_integration_oauth_to_metadata,
    enrich_skill_metadata_integration_oauth,
    wrap_integration_oauth_backend,
)
from .permission_logger import start_permission_logger
from .x_live_search_skill_enable import maybe_enable_x_live_search_skill

__all__ = [
    "GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE",
    "GOOGLE_WORKSPACE_SKILL_ID",
    "IntegrationOAuthSkillBackend",
    "LINEAR_PROJECT_SKILL_ID",
    "NOTION_WORKSPACE_SKILL_ID",
    "X_LIVE_SEARCH_SKILL_ID",
    "X_LIVE_SEARCH_UNAVAILABLE",
    "XURL_BIN_UNAVAILABLE",
    "XURL_SKILL_ID",
    "apply_integration_oauth_availability",
    "apply_integration_oauth_to_metadata",
    "collect_disabled_skill_roots",
    "enrich_skill_metadata_integration_oauth",
    "get_dependents_for_skill",
    "get_dependents_map",
    "maybe_enable_x_live_search_skill",
    "start_permission_logger",
    "wrap_integration_oauth_backend",
]
