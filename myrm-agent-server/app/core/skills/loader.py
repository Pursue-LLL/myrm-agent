"""技能加载工厂（业务层）

封装技能后端的组装逻辑，业务层一行调用即可获取完整的 SkillBackend。

框架层保持通用（只接受 SkillBackend 接口），业务逻辑（权限过滤、路径映射、
prebuilt/user/workspace 组合）全部在此处理。
"""

import asyncio
import logging
from pathlib import Path

from myrm_agent_harness.api import SkillBackend
from myrm_agent_harness.backends.skills import (
    CompositeSkillBackend,
    InMemorySkillBackend,
    LocalSkillBackend,
    QuarantineAwareSkillBackend,
    StorageSkillBackend,
    VersionAwareSkillBackend,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillTrust
from myrm_agent_harness.core.security.path import safe_join_path
from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)

PREBUILT_SKILLS_PREFIX = "skills/prebuilt"

WORKSPACE_SKILL_DIRS = (
    ".myrm/skills",
    ".cursor/skills",
    ".claude/skills",
    ".agents/skills",
    ".codex/skills",
    ".hermes/skills",
)


def _list_local_resources(skill_dir: Path) -> list[str]:
    try:
        return [
            str(item.relative_to(skill_dir))
            for item in skill_dir.rglob("*")
            if item.is_file() and not item.name.startswith(".") and item.name != "SKILL.md"
        ]
    except OSError:
        return []


class _UserSkillBackend:
    """用户技能后端（内部实现）

    技能以运行时名称列出；调用方可用该名称或元数据上的 storage_skill_id 取回内容。
    存储类技能（prebuilt）经 StorageProvider 按 storage_path 读取；LOCAL 技能位于
    StorageProvider 根之外的本机目录，直接从该目录读取。
    """

    def __init__(
        self,
        storage: StorageProvider,
        skills: list[SkillMetadata],
        local_skill_ids: frozenset[str] = frozenset(),
    ):
        self._storage = storage
        self._skills = skills
        self._local_skill_ids = local_skill_ids
        self._by_key = {key: skill for skill in skills for key in (skill.name, skill.storage_skill_id) if key}

    def _locate(self, skill_key: str) -> tuple[SkillMetadata, str]:
        skill = self._by_key.get(skill_key)
        if not skill or not skill.storage_path:
            raise FileNotFoundError(f"User skill not found: {skill_key}")
        return skill, skill.storage_path

    def _is_local(self, skill: SkillMetadata) -> bool:
        return skill.storage_skill_id in self._local_skill_ids

    async def list_skills(self) -> list[SkillMetadata]:
        return list(self._skills)

    async def load_skills(self, skill_ids: list[str]) -> list[SkillMetadata]:
        id_set = set(skill_ids)
        return [s for s in self._skills if s.name in id_set or s.storage_skill_id in id_set]

    async def get_skill_content(self, skill_name: str) -> str:
        skill, root = self._locate(skill_name)
        if self._is_local(skill):
            return await asyncio.to_thread((Path(root) / "SKILL.md").read_text, encoding="utf-8")
        return str(await self._storage.read_text(f"{root}/SKILL.md"))

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        skill, root = self._locate(skill_name)
        if self._is_local(skill):
            return await asyncio.to_thread(safe_join_path(root, path).read_bytes)
        return bytes(await self._storage.read(f"{root}/{path}"))

    async def list_skill_resources(self, skill_name: str) -> list[str]:
        try:
            skill, root = self._locate(skill_name)
        except FileNotFoundError:
            return []
        if self._is_local(skill):
            return await asyncio.to_thread(_list_local_resources, Path(root))
        prefix = f"{root}/"
        files = await self._storage.list(prefix=prefix)
        return [f[len(prefix) :] for f in files if not f.endswith("/SKILL.md")]


class _EnabledPrebuiltBackend(InMemorySkillBackend):
    """用户已启用的 prebuilt 技能：元数据驻留内存，内容与资源由 prebuilt 存储提供。"""

    def __init__(self, skills: list[SkillMetadata], store: SkillBackend):
        super().__init__(skills=skills)
        self._store = store
        self._enabled = frozenset(key for skill in skills for key in (skill.name, skill.storage_skill_id) if key)

    def _require_enabled(self, skill_key: str) -> None:
        if skill_key not in self._enabled:
            raise FileNotFoundError(f"Prebuilt skill not enabled: {skill_key}")

    async def get_skill_content(self, skill_name: str) -> str:
        self._require_enabled(skill_name)
        return await self._store.get_skill_content(skill_name)

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        self._require_enabled(skill_name)
        return await self._store.get_skill_resources(skill_name, path)

    async def list_skill_resources(self, skill_name: str) -> list[str]:
        if skill_name not in self._enabled:
            return []
        return await self._store.list_skill_resources(skill_name)


async def create_skill_backend(
    storage: StorageProvider,
    skill_ids: list[str] | None = None,
    user_id: str | None = None,
    workspace_path: str | None = None,
    allowed_prebuilt_ids: frozenset[str] | None = None,
) -> SkillBackend:
    """创建技能后端（业务层工厂）

    自动组装 prebuilt + user + workspace 技能后端。
    首次调用时自动同步 prebuilt_seeds 到存储。

    Args:
        storage: 存储后端（StorageProvider）
        skill_ids: 用户选择的技能 ID 列表（可选）
        user_id: 用户 ID（可选，权限过滤）
        workspace_path: 项目工作目录（可选，用于扫描项目级技能）
        allowed_prebuilt_ids: 用户启用的 prebuilt 技能 ID 白名单。
            None 或空集合 = 不挂载 prebuilt 后端；
            非空 = 仅挂载白名单内的 prebuilt 技能

    Returns:
        组装好的 SkillBackend
    """
    from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
    from app.core.skills.store.service import skills_service

    sync_result = await sync_prebuilt_seeds(storage)
    if sync_result.skill_ids:
        await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))

    prebuilt_backend = StorageSkillBackend(
        storage=storage,
        skills_prefix=PREBUILT_SKILLS_PREFIX,
        default_trust=SkillTrust.TRUSTED,
    )

    routes: dict[str, SkillBackend] = {}

    if skill_ids and user_id:
        user_backend = await _load_user_skill_backend(storage, skill_ids, user_id)
        if user_backend is not None:
            routes["/user/"] = user_backend
            logger.warning("📦 已加载 %d 个用户技能", len(skill_ids))

    if allowed_prebuilt_ids is not None and len(allowed_prebuilt_ids) > 0:
        all_prebuilt = await prebuilt_backend.list_skills()
        filtered = [s for s in all_prebuilt if s.name in allowed_prebuilt_ids]
        if filtered:
            routes["/prebuilt/"] = _EnabledPrebuiltBackend(filtered, prebuilt_backend)
            logger.info(
                "Prebuilt whitelist: %d/%d skills allowed",
                len(filtered),
                len(all_prebuilt),
            )

    workspace_backend = _load_workspace_skill_backend(workspace_path)
    if workspace_backend is not None:
        routes["/workspace/"] = workspace_backend

    if allowed_prebuilt_ids is not None:
        if not routes:
            final_backend: SkillBackend = InMemorySkillBackend(skills=[])
            logger.info("Action space: 0 prebuilt skills (whitelist is empty)")
        else:
            final_backend = CompositeSkillBackend(routes=routes)
    elif not routes:
        logger.info("只加载内置技能（从对象存储：%s/）", PREBUILT_SKILLS_PREFIX)
        final_backend = prebuilt_backend
    else:
        final_backend = CompositeSkillBackend(routes=routes, default=prebuilt_backend)

    # Quarantine awareness: runtime state filtering via SkillStateReader protocol
    from app.core.skills.state_reader import SQLiteSkillStateReader

    state_reader = SQLiteSkillStateReader()
    quarantine_backend = QuarantineAwareSkillBackend(base_backend=final_backend, state_reader=state_reader)

    from app.core.skills.gates.oauth_availability import wrap_integration_oauth_backend

    runtime_backend: SkillBackend = quarantine_backend

    # Version awareness: A/B testing and snapshot routing via storage protocols
    try:
        from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
        from app.core.skills.storage_adapters import ABTestStoreAdapter, SnapshotStoreAdapter
        from app.platform_utils import get_session_factory

        session_factory = get_session_factory()
        session = session_factory()
        db_storage = SQLAlchemyStorage(session)

        runtime_backend = VersionAwareSkillBackend(
            base_backend=quarantine_backend,
            snapshot_store=SnapshotStoreAdapter(db_storage),
            ab_test_store=ABTestStoreAdapter(db_storage),
        )
    except ImportError:
        logger.warning("Skill optimization storage not available, disabled version awareness")
    except Exception as e:
        logger.error("Failed to initialize VersionAwareSkillBackend: %s", e)

    return wrap_integration_oauth_backend(runtime_backend)


def _load_workspace_skill_backend(
    workspace_path: str | None,
) -> SkillBackend | None:
    """Load project-level and cross-harness skills from workspace directory.

    Scans configured workspace skill directories (.myrm/skills, .cursor/skills,
    .claude/skills, .agents/skills, .codex/skills, .hermes/skills).
    Returns a unified LocalSkillBackend or CompositeSkillBackend for multi-source skills.
    """
    if not workspace_path:
        return None

    root = Path(workspace_path)
    if not root.is_dir():
        return None

    valid_backends: list[LocalSkillBackend] = []
    for skill_dir_name in WORKSPACE_SKILL_DIRS:
        skills_dir = root / skill_dir_name
        if skills_dir.is_dir() and any(skills_dir.iterdir()):
            try:
                backend = LocalSkillBackend(skills_dir)
                logger.warning("📂 已加载项目/跨生态技能目录: %s", skills_dir)
                valid_backends.append(backend)
            except (FileNotFoundError, ValueError) as e:
                logger.warning("⚠️ 技能目录无效 %s: %s", skills_dir, e)

    if not valid_backends:
        return None
    if len(valid_backends) == 1:
        return valid_backends[0]

    routes = {f"/src_{i}/": b for i, b in enumerate(valid_backends)}
    return CompositeSkillBackend(routes=routes, default=valid_backends[0])


async def _load_user_skill_backend(
    storage: StorageProvider,
    skill_ids: list[str],
    user_id: str,
) -> _UserSkillBackend | None:
    """加载用户技能后端（内部）"""
    from app.core.skills.models import SkillType
    from app.core.skills.store.service import skills_service
    from app.core.skills.utils import normalize_skill_name

    try:
        skills = await skills_service.get_skills_by_ids(skill_ids=skill_ids)
        if not skills:
            logger.warning(f"No skills found for user {user_id} with IDs {skill_ids}")
            return None

        metadata_list: list[SkillMetadata] = []
        for skill in skills:
            try:
                name = normalize_skill_name(skill.name)
            except ValueError as e:
                logger.warning(f"Skipping skill with invalid name '{skill.name}': {e}")
                continue
            metadata_list.append(
                SkillMetadata(
                    name=name,
                    description=skill.description,
                    storage_skill_id=skill.id,
                    storage_path=skill.storage_path,
                    token_cost=skill.token_cost,
                )
            )

        if not metadata_list:
            return None

        local_skill_ids = frozenset(skill.id for skill in skills if skill.type == SkillType.LOCAL)
        return _UserSkillBackend(storage=storage, skills=metadata_list, local_skill_ids=local_skill_ids)

    except Exception as e:
        logger.error(f"Failed to load user skills for {user_id}: {e}")
        return None
