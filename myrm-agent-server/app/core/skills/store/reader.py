"""技能读取操作

提供技能的列表查询和文件读取功能，作为 SkillsService 的底层实现。
"""

from __future__ import annotations

import json
import logging
import mimetypes
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.paths import (
    SKILL_METADATA_FILE,
    get_skills_type_prefix,
)

from ..models import Skill, SkillType
from .user_config import UserSkillConfigManager

logger = logging.getLogger(__name__)

# ========================================================================
# 列表操作
# ========================================================================


async def list_prebuilt_skills(storage: StorageProvider) -> list[Skill]:
    """列出所有预构建技能"""
    skills: list[Skill] = []
    try:
        prebuilt_prefix = get_skills_type_prefix(SkillType.PREBUILT)
        prebuilt_files = await storage.list(prebuilt_prefix)
        for file_path in prebuilt_files:
            if file_path.endswith(SKILL_METADATA_FILE):
                try:
                    content = await storage.read_text(file_path)
                    skill = Skill.from_dict(json.loads(content))
                    if skill.is_active:
                        skills.append(skill)
                except Exception as e:
                    logger.warning(f"Failed to load skill from {file_path}: {e}")
    except Exception:
        pass
    return skills


async def list_local_skills(
    user_config: UserSkillConfigManager,
) -> list[Skill]:
    """List local skills (disabled in sandbox mode)."""
    from ..providers.local import LocalSkillsProvider, is_sandbox_mode

    if is_sandbox_mode():
        return []

    config = await user_config.get_config()
    user_paths = config.local_skill_paths

    from ..models import DEFAULT_LOCAL_SKILL_PATHS

    all_paths = DEFAULT_LOCAL_SKILL_PATHS.copy()
    for path in user_paths:
        if path not in all_paths:
            all_paths.append(path)

    provider = LocalSkillsProvider(all_paths)
    return provider.scan_all()


def list_workspace_skills(workspace_root: str | None) -> list[Skill]:
    """Scan workspace directory for project-level SKILL.md files."""
    if not workspace_root:
        return []
    from ..providers.local import scan_workspace_skills

    return scan_workspace_skills(workspace_root)


def _ensure_aware(dt: datetime | None) -> datetime:
    """Normalize a datetime to timezone-aware UTC for safe comparisons."""
    if dt is None:
        return datetime(1970, 1, 1, tzinfo=UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def sort_skills(skills: list[Skill], sort_by: str, order: str) -> list[Skill]:
    """排序技能列表"""
    reverse = order == "desc"
    if sort_by == "created_at":
        skills.sort(key=lambda s: _ensure_aware(s.created_at), reverse=reverse)
    elif sort_by == "updated_at":
        skills.sort(key=lambda s: _ensure_aware(s.updated_at), reverse=reverse)
    else:
        skills.sort(key=lambda s: s.name.lower(), reverse=reverse)
    return skills


# ========================================================================
# 文件操作
# ========================================================================


async def get_skill_file(
    skill: Skill | None,
    filename: str,
    storage: StorageProvider,
) -> bytes | None:
    """获取技能文件内容"""
    if not skill:
        return None

    if skill.type == SkillType.LOCAL:
        from pathlib import Path

        file_path = Path(skill.storage_path) / filename
        try:
            return file_path.read_bytes()
        except (FileNotFoundError, PermissionError):
            return None

    storage_key = f"{skill.storage_path}/{filename}"
    try:
        return bytes(await storage.read(storage_key))
    except FileNotFoundError:
        return None


async def list_skill_files(
    skill: Skill | None,
    storage: StorageProvider,
) -> list[str]:
    """列出技能的所有文件"""
    if not skill:
        return []

    if skill.type == SkillType.LOCAL:
        from pathlib import Path

        skill_dir = Path(skill.storage_path)
        files: list[str] = []
        try:
            for item in skill_dir.rglob("*"):
                if item.is_file() and not item.name.startswith("."):
                    files.append(str(item.relative_to(skill_dir)))
        except (PermissionError, OSError):
            pass
        return files

    storage_files = await storage.list(skill.storage_path)
    prefix_len = len(skill.storage_path) + 1
    return [f[prefix_len:] for f in storage_files if len(f) > prefix_len]


async def download_skill_to_workspace(
    skill: Skill | None,
    target_path: str,
    storage: StorageProvider,
    target_storage: StorageProvider | None = None,
    force: bool = False,
) -> bool:
    """下载技能的所有文件到目标路径（支持版本号增量下载）"""
    if not skill:
        return False

    dest_storage = target_storage or storage
    metadata_dest = f"{target_path}/{SKILL_METADATA_FILE}"

    if not force:
        try:
            dest_metadata_content = await dest_storage.read_text(metadata_dest)
            dest_metadata = json.loads(dest_metadata_content)
            dest_version = dest_metadata.get("version", "0.0.0")

            if dest_version == skill.version:
                logger.debug(f"⏭️ Skill already up-to-date: {skill.id} (v{skill.version})")
                return True
            else:
                logger.warning(f"🔄 Skill version changed: {skill.id} ({dest_version} -> {skill.version}), updating...")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    downloaded_count = 0

    if skill.type == SkillType.LOCAL:
        downloaded_count = await _download_local_skill(skill, target_path, dest_storage)
    else:
        downloaded_count = await _download_storage_skill(skill, target_path, storage, dest_storage)

    if downloaded_count > 0:
        logger.warning(f"📦 Skill downloaded: {skill.id} v{skill.version} -> {target_path} ({downloaded_count} files)")

        # Trigger fast O(1) snapshot upsert for the downloaded skill
        import asyncio
        from pathlib import Path

        try:
            workspace_root = Path(target_path).parent.parent.parent
            if (workspace_root / ".myrm").exists():
                from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot
                
                snapshot_path = workspace_root / ".skills_snapshot.sqlite"
                skill_md_path = Path(target_path) / "SKILL.md"
                
                def _do_upsert():
                    snapshot = SQLiteSkillSnapshot(snapshot_path)
                    snapshot.upsert_from_path(skill_md_path, workspace_root=workspace_root)

                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _do_upsert)
        except Exception as e:
            logger.warning(f"Failed to trigger workspace snapshot upsert: {e}")

    return downloaded_count > 0


async def _download_local_skill(
    skill: Skill,
    target_path: str,
    dest_storage: StorageProvider,
) -> int:
    """下载本地技能文件"""
    from pathlib import Path

    downloaded_count = 0
    skill_dir = Path(skill.storage_path)
    try:
        for item in skill_dir.rglob("*"):
            if item.is_file() and not item.name.startswith("."):
                try:
                    relative_path = str(item.relative_to(skill_dir))
                    dest_path = f"{target_path}/{relative_path}"
                    content = item.read_bytes()
                    content_type, _ = mimetypes.guess_type(relative_path)
                    await dest_storage.write(dest_path, content, content_type)
                    downloaded_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Failed to copy local file {item}: {e}")
    except (PermissionError, OSError) as e:
        logger.warning(f"⚠️ Failed to access local skill directory: {e}")
    return downloaded_count


async def _download_storage_skill(
    skill: Skill,
    target_path: str,
    storage: StorageProvider,
    dest_storage: StorageProvider,
) -> int:
    """下载存储技能文件"""
    downloaded_count = 0
    files = await storage.list(skill.storage_path)
    for file_path in files:
        try:
            relative_path = file_path[len(skill.storage_path) + 1 :]
            if not relative_path:
                continue

            dest_path = f"{target_path}/{relative_path}"
            content = await storage.read(file_path)
            if content is None:
                continue

            content_type, _ = mimetypes.guess_type(relative_path)
            await dest_storage.write(dest_path, content, content_type)
            downloaded_count += 1
        except Exception as e:
            logger.warning(f"⚠️ Failed to download file {file_path}: {e}")
    return downloaded_count
