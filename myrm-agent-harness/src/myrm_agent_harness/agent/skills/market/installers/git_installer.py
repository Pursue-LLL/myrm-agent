"""Git 技能安装器

通过 git clone --depth 1 下载技能仓库，提取 SKILL.md 和相关文件。克隆出来的一切都不可信：
技能目录必须落在克隆之内；符号链接只有在真实目标仍在克隆之内时才会被跟随；
文件大小在读入内存之前就按安装时同一套限额检查。

[INPUT]
- core.security.path::is_within_boundary, safe_join_path (POS: real-path containment of the clone)
- agent.skills.market.sanitizer::is_blocked_file, check_size_budget (POS: the same file filter and size limits the install step applies)

[OUTPUT]
- GitInstaller: class — Git Installer

[POS]
Provides GitInstaller.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from myrm_agent_harness.core.security.path import is_within_boundary, safe_join_path

from ..sanitizer import SKILL_MD_FILE, check_size_budget, is_blocked_file
from .base import InstalledSkillFiles

logger = logging.getLogger(__name__)

GIT_CLONE_TIMEOUT = 60
_EXCLUDED_DIR_NAMES = frozenset({"__pycache__", "node_modules"})


class GitInstaller:
    """Git 技能安装器

    浅克隆仓库 → 定位 SKILL.md → 收集文件 → 清理临时目录。
    """

    async def download(
        self, install_url: str, subdirectory: str | None = None, ref: str | None = None
    ) -> InstalledSkillFiles:
        """Download a skill from a git repository.

        Args:
            install_url: Git clone URL
            subdirectory: Optional subdirectory within the repo containing the skill
            ref: Optional branch, tag, or commit to checkout
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="skill_git_"))
        try:
            await self._git_clone(install_url, tmp_dir, ref=ref)
            # Directory scans and file reads block; keep them off the event loop.
            return await asyncio.to_thread(self._extract, tmp_dir, subdirectory)
        finally:
            await asyncio.to_thread(shutil.rmtree, tmp_dir, ignore_errors=True)

    def _extract(self, repo_root: Path, subdirectory: str | None) -> InstalledSkillFiles:
        skill_dir = self._resolve_skill_dir(repo_root, subdirectory)
        return self._collect_skill_files(skill_dir, repo_root)

    @staticmethod
    def _resolve_skill_dir(repo_root: Path, subdirectory: str | None) -> Path:
        """Resolve the actual skill directory within a cloned repo.

        Strategy: exact path → exact directory name match → substring match
        among all SKILL.md candidates. Handles cases where the skill name in
        the registry differs from the actual directory name in the repo.

        Raises:
            ValueError: ``subdirectory`` leaves the repository (``..``, an absolute
                path, or a symlink pointing outside), so its files must not be installed.
        """
        if not subdirectory:
            return repo_root

        exact = safe_join_path(repo_root, subdirectory)
        if exact.exists() and (exact / SKILL_MD_FILE).exists():
            return exact

        skill_name = subdirectory.split("/")[-1].lower()
        candidates = [p for p in repo_root.rglob(SKILL_MD_FILE) if ".git" not in p.parts]

        for candidate in candidates:
            if candidate.parent.name.lower() == skill_name:
                return candidate.parent

        for candidate in candidates:
            dir_name = candidate.parent.name.lower()
            if dir_name in skill_name or skill_name in dir_name:
                return candidate.parent

        if exact.exists():
            return exact

        if len(candidates) == 1:
            return candidates[0].parent

        return repo_root

    async def _git_clone(self, url: str, target: Path, *, ref: str | None = None) -> None:
        cmd = ["git", "clone", "--depth", "1", "--single-branch"]
        if ref:
            cmd.extend(["--branch", ref])
        cmd.extend([url, str(target)])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=GIT_CLONE_TIMEOUT)
        except TimeoutError:
            proc.kill()
            raise ValueError(f"Git clone timed out after {GIT_CLONE_TIMEOUT}s: {url}") from None

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip() if stderr else "unknown error"
            raise ValueError(f"Git clone failed: {error_msg}")

    def _collect_skill_files(self, skill_dir: Path, boundary: Path | None = None) -> InstalledSkillFiles:
        """Read the skill's files; ``boundary`` is the clone root (default: ``skill_dir``).

        Raises:
            ValueError: no SKILL.md, or a file or the total crosses the install size limits.
        """
        clone_root = skill_dir if boundary is None else boundary
        if not _is_usable_file(skill_dir / SKILL_MD_FILE, clone_root):
            found = _find_skill_md(skill_dir, boundary=clone_root)
            if found is None:
                raise ValueError(f"SKILL.md not found in {skill_dir}")
            skill_dir = found.parent

        files: dict[str, bytes] = {}
        total_size = 0
        name = skill_dir.name
        description = ""

        for item in _walk_skill_dir(skill_dir, clone_root):
            rel_path = str(item.relative_to(skill_dir))
            if is_blocked_file(rel_path):
                continue
            try:
                total_size = check_size_budget(rel_path, item.stat().st_size, total_size)
                files[rel_path] = item.read_bytes()
            except OSError as e:
                logger.warning(f"Failed to read {item}: {e}")

        if SKILL_MD_FILE in files:
            name, description = _parse_skill_md_metadata(files[SKILL_MD_FILE])

        return InstalledSkillFiles(name=name, description=description, files=files)


def _escapes_clone(item: Path | str, boundary: Path) -> bool:
    """True when a symlink's real target is outside ``boundary``; such a link is never followed."""
    if is_within_boundary(item, boundary):
        return False
    logger.warning(f"Skipping symlink that leaves the cloned repository: {item}")
    return True


def _is_usable_file(path: Path, boundary: Path) -> bool:
    """A regular file, or a symlink to one that stays inside ``boundary``."""
    if path.is_symlink() and _escapes_clone(path, boundary):
        return False
    return path.is_file()


def _find_skill_md(root: Path, max_depth: int = 3, boundary: Path | None = None) -> Path | None:
    """在目录树中查找 SKILL.md（限制深度避免超大仓库扫描；链接目标在 boundary 之外的不跟随）"""
    if max_depth <= 0:
        return None
    clone_root = root if boundary is None else boundary
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink() and _escapes_clone(entry.path, clone_root):
                        continue
                    if entry.name == SKILL_MD_FILE and entry.is_file():
                        return Path(entry.path)
                    if not entry.name.startswith(".") and entry.is_dir():
                        result = _find_skill_md(Path(entry.path), max_depth - 1, clone_root)
                        if result:
                            return result
                except OSError:
                    continue  # an entry that cannot be examined (a link loop) is skipped, the search goes on
    except OSError:
        pass
    return None


def _walk_skill_dir(skill_dir: Path, boundary: Path | None = None) -> list[Path]:
    """收集技能目录中的所有文件（排除隐藏文件和常见垃圾目录）

    只看技能目录之内的名称：技能目录自身的祖先（如以点开头的临时目录）不参与排除，
    被排除的目录不会进入。符号链接目录不进入；符号链接文件只有在真实目标位于
    ``boundary``（默认技能目录自身）之内时才收集，其余跳过。无法检查的条目（如符号链接环）
    只跳过它自己，不影响同一目录里的其它文件。
    """
    clone_root = skill_dir if boundary is None else boundary
    files: list[Path] = []
    pending = [skill_dir]

    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name.startswith(".") or entry.name in _EXCLUDED_DIR_NAMES:
                        continue
                    try:
                        if entry.is_symlink() and _escapes_clone(entry.path, clone_root):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file():
                            files.append(Path(entry.path))
                    except OSError as e:
                        logger.warning(f"Skipping {entry.path}: {e}")
        except OSError as e:
            logger.warning(f"Cannot read directory {current}: {e}")

    return files


def _parse_skill_md_metadata(content: bytes) -> tuple[str, str]:
    """从 SKILL.md 解析 name 和 description"""
    text = content.decode("utf-8", errors="replace")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return "unnamed_skill", ""
    try:
        frontmatter = yaml.safe_load(match.group(1))
        if isinstance(frontmatter, dict):
            name = str(frontmatter.get("name", "unnamed_skill"))
            description = str(frontmatter.get("description", ""))
            return name, description
    except Exception:
        pass
    return "unnamed_skill", ""
