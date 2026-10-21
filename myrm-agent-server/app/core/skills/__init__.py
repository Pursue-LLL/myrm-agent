"""Skills module - 业务层技能管理

提供：
- models: Skill, UserSkillConfig 等业务数据模型
- store: 技能 CRUD 服务、用户配置
- packaging: 技能打包/解包
- providers: 技能提供者（本地文件系统）
- loader: 技能后端工厂（组装 SkillBackend）
"""

from app.core.skills.loader import create_skill_backend
from app.core.skills.models import (
    DEFAULT_LOCAL_SKILL_PATHS,
    Skill,
    SkillType,
    UserSkillConfig,
)
from app.core.skills.packaging import (
    SkillPackagingService,
    skill_packaging_service,
)
from app.core.skills.providers.local import (
    LocalSkillsProvider,
    get_local_skills_provider,
    is_sandbox_mode,
)
from app.core.skills.store.service import (
    SKILL_MD_FILE,
    SKILL_NAME_PATTERN,
    SkillsService,
    skills_service,
)
from app.core.skills.store.user_config import UserSkillConfigManager
from app.core.skills.utils import normalize_skill_name

__all__ = [
    # Models
    "Skill",
    "SkillType",
    "UserSkillConfig",
    "DEFAULT_LOCAL_SKILL_PATHS",
    # Store
    "SkillsService",
    "skills_service",
    "SKILL_NAME_PATTERN",
    "SKILL_MD_FILE",
    "UserSkillConfigManager",
    # Packaging
    "SkillPackagingService",
    "skill_packaging_service",
    # Providers
    "LocalSkillsProvider",
    "get_local_skills_provider",
    "is_sandbox_mode",
    # Loader
    "create_skill_backend",
    "normalize_skill_name",
]
