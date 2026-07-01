"""本地技能扫描服务

提供从本地文件系统扫描技能的功能。
内部委托给框架层 LocalSkillBackend 进行实际的 SKILL.md 解析和验证，
然后通过 Skill.from_metadata() 适配为业务层模型。

默认扫描路径：~/.myrm/skills
用户可通过前端配置额外的本地路径。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from myrm_agent_harness.api.skills import (
    SkillMetadataError,
    build_skill_metadata,
    parse_skill_frontmatter,
)
from myrm_agent_harness.backends.skills.types import SkillTrust, SkillUsageStats

from ..models import DEFAULT_LOCAL_SKILL_PATHS, Skill, SkillType

logger = logging.getLogger(__name__)

SKILL_MD_FILE = "SKILL.md"

_MAX_SKILL_FILE_SIZE = 1 * 1024 * 1024  # 1 MB


def is_sandbox_mode() -> bool:
    """是否为沙箱模式（本地技能在沙箱中不可用）"""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    return not get_deployment_capabilities().allows_local_skills


def parse_skill_md(content: str) -> dict[str, object] | None:
    """Parse SKILL.md YAML frontmatter into a raw metadata dict.

    Thin wrapper for backward compatibility with packaging validators.
    For full validation, use the framework's parse_skill_frontmatter() directly.
    """
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not frontmatter_match:
        return None

    try:
        yaml_mod = importlib.import_module("yaml")
        frontmatter = yaml_mod.safe_load(frontmatter_match.group(1))
        if isinstance(frontmatter, dict):
            return {str(k): v for k, v in frontmatter.items()}
        return None
    except Exception:
        return None


def compute_local_skill_id(path: Path) -> str:
    """Compute a stable ID for a local skill based on its resolved path."""
    path_str = str(path.resolve())
    path_hash = hashlib.sha256(path_str.encode("utf-8")).hexdigest()[:16]
    return f"local::{path_hash}"


def expand_path(path: str) -> Path:
    """Expand ~ and resolve to absolute path."""
    expanded = os.path.expanduser(path)
    return Path(expanded).resolve()


def validate_path(path: Path) -> bool:
    """Validate path security (no traversal, must be absolute)."""
    path_str = str(path)
    if ".." in path_str:
        return False
    if not path.is_absolute():
        return False
    return True


def _load_skill_from_dir(
    skill_dir: Path,
    skill_type: SkillType,
    id_prefix: str,
    trust: SkillTrust = SkillTrust.TRUSTED,
) -> Skill | None:
    """Load a skill from a directory using framework-layer parsing.

    Delegates SKILL.md parsing and validation to the framework's
    parse_skill_frontmatter + build_skill_metadata, then adapts to Skill.
    """
    skill_md_path = skill_dir / SKILL_MD_FILE

    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read {skill_md_path}: {e}")
        return None

    if len(content.encode("utf-8")) > _MAX_SKILL_FILE_SIZE:
        logger.warning(f"Skipping '{skill_dir.name}': SKILL.md exceeds 1 MB limit")
        return None

    try:
        frontmatter = parse_skill_frontmatter(content, skill_dir.name)
    except SkillMetadataError as e:
        logger.warning(f"Invalid skill '{skill_dir.name}': {e}")
        return None

    meta = build_skill_metadata(
        skill_name=skill_dir.name,
        frontmatter=frontmatter,
        storage_path=str(skill_dir.resolve()),
        content=content,
        trust=trust,
    )

    stats_file = skill_dir / ".stats.json"
    if stats_file.exists():
        try:
            stats_data = json.loads(stats_file.read_text(encoding="utf-8"))
            object.__setattr__(meta, "usage_stats", SkillUsageStats.from_dict(stats_data))
        except Exception as e:
            logger.debug("Failed to load .stats.json for '%s': %s", skill_dir.name, e)

    path_hash = hashlib.sha256(str(skill_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    skill_id = f"{id_prefix}::{path_hash}"

    category = frontmatter.category

    try:
        stat = skill_dir.stat()
        created_at = datetime.fromtimestamp(stat.st_ctime)
        updated_at = datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        created_at = datetime.utcnow()
        updated_at = datetime.utcnow()

    return Skill.from_metadata(
        meta,
        skill_id=skill_id,
        skill_type=skill_type,
        category=category,
        created_at=created_at,
        updated_at=updated_at,
    )


class LocalSkillsProvider:
    """本地技能扫描提供者

    扫描本地文件系统中的技能目录，生成 Skill 对象列表。
    内部委托给框架层的 parse_skill_frontmatter + build_skill_metadata
    进行 SKILL.md 解析和验证。
    """

    def __init__(self, paths: list[str] | None = None):
        self._paths = paths if paths is not None else DEFAULT_LOCAL_SKILL_PATHS.copy()

    @property
    def paths(self) -> list[str]:
        return self._paths

    def set_paths(self, paths: list[str]) -> None:
        self._paths = paths

    def add_path(self, path: str) -> bool:
        if path not in self._paths:
            self._paths.append(path)
            return True
        return False

    def remove_path(self, path: str) -> bool:
        if path in self._paths:
            self._paths.remove(path)
            return True
        return False

    def scan_all(self) -> list[Skill]:
        """Scan all configured paths for skills."""
        if is_sandbox_mode():
            logger.warning("Local skills scanning is disabled in sandbox mode")
            return []

        skills: list[Skill] = []

        for path_str in self._paths:
            try:
                path = expand_path(path_str)
                if not validate_path(path):
                    logger.warning(f"Invalid path (security check failed): {path_str}")
                    continue

                if not path.exists():
                    logger.warning(f"Local skills path does not exist: {path}")
                    continue

                if not path.is_dir():
                    logger.warning(f"Local skills path is not a directory: {path}")
                    continue

                path_skills = self.scan_path(path)
                skills.extend(path_skills)

            except Exception as e:
                logger.warning(f"Failed to scan path {path_str}: {e}")

        return skills

    def scan_path(self, path: Path) -> list[Skill]:
        """Scan a single directory for skills (one level deep)."""
        skills: list[Skill] = []

        try:
            for item in path.iterdir():
                if not item.is_dir():
                    continue

                skill_md_path = item / SKILL_MD_FILE
                if not skill_md_path.exists():
                    continue

                try:
                    skill = _load_skill_from_dir(item, SkillType.LOCAL, "local")
                    if skill:
                        skills.append(skill)
                except Exception as e:
                    logger.warning(f"Failed to load skill from {item}: {e}")

        except PermissionError:
            logger.warning(f"Permission denied accessing {path}")
        except Exception as e:
            logger.warning(f"Failed to scan directory {path}: {e}")

        return skills

    def get_skill_by_id(self, skill_id: str) -> Skill | None:
        """Look up a skill by ID (requires re-scanning all paths)."""
        if not skill_id.startswith("local::"):
            return None

        all_skills = self.scan_all()
        for skill in all_skills:
            if skill.id == skill_id:
                return skill
        return None

    def get_skill_files(self, skill: Skill) -> dict[str, bytes]:
        """Get all files for a local skill."""
        if skill.type != SkillType.LOCAL:
            raise ValueError(f"Skill {skill.id} is not a local skill")

        skill_dir = Path(skill.storage_path)
        if not skill_dir.exists() or not skill_dir.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

        files: dict[str, bytes] = {}
        self._collect_files(skill_dir, skill_dir, files)
        return files

    def _collect_files(self, base_dir: Path, current_dir: Path, files: dict[str, bytes]) -> None:
        try:
            for item in current_dir.iterdir():
                if item.name.startswith(".") or item.name == "__pycache__" or item.name.startswith("_"):
                    continue

                if item.is_file():
                    try:
                        relative_path = str(item.relative_to(base_dir))
                        files[relative_path] = item.read_bytes()
                    except Exception as e:
                        logger.warning(f"Failed to read file {item}: {e}")
                elif item.is_dir():
                    self._collect_files(base_dir, item, files)

        except PermissionError:
            logger.warning(f"Permission denied accessing {current_dir}")


def scan_workspace_skills(workspace_root: str, max_depth: int = 3) -> list[Skill]:
    """Scan a workspace directory for SKILL.md files (project-level skills).

    Delegates to the framework-layer scan_workspace_skills() for actual discovery,
    then adapts each SkillMetadata to a business-layer Skill.
    """
    from myrm_agent_harness.backends.skills.local import (
        scan_workspace_skills as _fw_scan,
    )

    metadatas = _fw_scan(workspace_root, max_depth=max_depth, trust=SkillTrust.INSTALLED)

    skills: list[Skill] = []
    for meta in metadatas:
        path_hash = hashlib.sha256((meta.storage_path or "").encode("utf-8")).hexdigest()[:16]
        skill_id = f"workspace::{path_hash}"

        skill_dir = Path(meta.storage_path or "")
        try:
            stat = skill_dir.stat()
            created_at = datetime.fromtimestamp(stat.st_ctime)
            updated_at = datetime.fromtimestamp(stat.st_mtime)
        except Exception:
            created_at = datetime.utcnow()
            updated_at = datetime.utcnow()

        skills.append(
            Skill.from_metadata(
                meta,
                skill_id=skill_id,
                skill_type=SkillType.WORKSPACE,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
    return skills


_local_skills_provider: LocalSkillsProvider | None = None


def get_local_skills_provider() -> LocalSkillsProvider:
    global _local_skills_provider
    if _local_skills_provider is None:
        _local_skills_provider = LocalSkillsProvider()
    return _local_skills_provider
