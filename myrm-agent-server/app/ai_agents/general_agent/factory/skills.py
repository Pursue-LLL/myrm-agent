"""[INPUT]
- myrm_agent_harness.backends.skills.protocols::SkillBackend (POS: Skill backend protocol definition. Specifies the unified interface for loading skills from multiple sources.)
- myrm_agent_harness.toolkits.storage.base::StorageProvider (POS: Storage provider abstract base class. Defines the unified storage interface contract for all storage backends.)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现。管理 Agent 初始化与流式执行， 工具创建委托给 ToolSetupMixin，资源释放委托给 AgentLifecycleMixin。)
- app.core.skills.models::UserSkillConfig (POS: Skill system data models.)
- app.core.skills.effective_skill_ids::resolve_runtime_skill_ids (POS: Runtime skill ID resolver. Strictly respects explicit Agent profile allowlist: WYSIWYG standard — if profile_skill_ids is empty or None, returns empty list [].)
- app.core.skills.loader::create_skill_backend (POS: Business-layer skill backend factory. The framework layer only accepts the SkillBackend interface; permission filtering, path mapping and the prebuilt / user / workspace composition are decided here, then wrapped with version routing (snapshot / A/B) and the integration-OAuth availability gate.)
- app.core.skills.store.user_config::UserSkillConfigManager (POS: 用户技能配置管理)
- app.platform_utils::get_storage_provider (POS: 平台适配层)

[OUTPUT]
- SkillRuntime: SkillRuntime
- load_skill_runtime: load_skill_runtime

[POS]
装配第二阶段；只解析技能可见性，不创建工具。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.protocols import SkillBackend
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.core.skills.models import UserSkillConfig


@dataclass(slots=True)
class SkillRuntime:
    storage_backend: "StorageProvider"
    user_skill_cfg: "UserSkillConfig"
    allowed_prebuilt: frozenset[str]
    runtime_skill_ids: list[str]
    skill_backend: "SkillBackend | None"


async def load_skill_runtime(
    agent_wrapper: "GeneralAgent",
    user_id: str,
    workspace_root: str | None,
) -> SkillRuntime:
    from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
    from app.core.skills.loader import create_skill_backend
    from app.core.skills.store.user_config import UserSkillConfigManager
    from app.platform_utils import get_storage_provider

    storage_backend = get_storage_provider()

    # 3. Load Skills (prebuilt visibility follows the user's enabled-prebuilt set)
    workspace_root = agent_wrapper.declared_allowed_roots[0] if agent_wrapper.declared_allowed_roots else None

    _user_skill_cfg = await UserSkillConfigManager(storage_backend).get_config()
    allowed_prebuilt = frozenset(_user_skill_cfg.enabled_prebuilt_ids)
    runtime_skill_ids = await resolve_runtime_skill_ids(agent_wrapper.skill_ids)

    skill_backend = await create_skill_backend(
        storage=storage_backend,
        skill_ids=runtime_skill_ids or None,
        user_id=user_id,
        workspace_path=workspace_root,
        allowed_prebuilt_ids=allowed_prebuilt,
        credential_track=agent_wrapper.credential_track,
    )

    return SkillRuntime(
        storage_backend=storage_backend,
        user_skill_cfg=_user_skill_cfg,
        allowed_prebuilt=allowed_prebuilt,
        runtime_skill_ids=runtime_skill_ids,
        skill_backend=skill_backend,
    )
