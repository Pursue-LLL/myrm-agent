"""The shipped prebuilt seeds as a catalog: each parses and syncs, names only registered tools, and the defaults exist."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills._utils import (
    SkillFrontmatter,
    SkillMetadataError,
    parse_skill_frontmatter,
)
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.store.reader import list_prebuilt_skills
from app.core.skills.store.user_config import _DEFAULT_ENABLED_PREBUILT_SKILLS


def _load_registered_tool_names() -> set[str]:
    harness_root = Path(__file__).resolve().parents[3].parent / "myrm-agent-harness"
    harness_src = str(harness_root)
    if harness_src not in sys.path:
        sys.path.insert(0, harness_src)
    from scripts.tool_registry_engine import load_registered_names

    names: set[str] = load_registered_names()
    return names


def _iter_prebuilt_seeds() -> Iterator[tuple[str, SkillFrontmatter]]:
    """遍历官方种子目录，产出 (目录名, frontmatter)；跳过非目录与元数据非法的种子。"""
    seeds_dir = Path(prebuilt_sync.__file__).resolve().parents[3] / "assets" / "prebuilt_skills"
    for skill_dir in sorted(seeds_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.exists():
            continue
        try:
            yield skill_dir.name, parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"), skill_dir.name)
        except SkillMetadataError:
            continue


def _iter_prebuilt_seed_skill_ids() -> set[str]:
    """种子库真实 skill_id 集合，取值口径与 prebuilt_sync 落盘一致（frontmatter 优先、目录名兜底）。"""
    return {frontmatter.name or dir_name for dir_name, frontmatter in _iter_prebuilt_seeds()}


def _iter_prebuilt_seed_allowed_tools() -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    for dir_name, frontmatter in _iter_prebuilt_seeds():
        if not frontmatter.allowed_tools:
            continue
        entries.append((dir_name, frontmatter.allowed_tools.split()))
    return entries


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def reset_sync_flag() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


def test_default_enabled_prebuilt_skills_resolve_to_real_seeds() -> None:
    """默认精选集必须逐个命中真实种子 skill_id，否则新装默认集会静默退化为空且无告警。"""
    assert set(_DEFAULT_ENABLED_PREBUILT_SKILLS) <= _iter_prebuilt_seed_skill_ids()


@pytest.mark.asyncio
async def test_all_prebuilt_seeds_parse_and_sync(storage: LocalStorageBackend) -> None:
    """Verify every SKILL.md in prebuilt_seeds has valid frontmatter and syncs successfully."""
    seeds_dir = Path(prebuilt_sync.__file__).resolve().parents[3] / "assets" / "prebuilt_skills"
    expected_dirs = {d.name for d in seeds_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()}

    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    synced_ids = set(result.skill_ids)
    assert synced_ids == expected_dirs, (
        f"Synced IDs mismatch. Missing: {expected_dirs - synced_ids}, Extra: {synced_ids - expected_dirs}"
    )
    assert result.synced_count == len(expected_dirs)

    skills = await list_prebuilt_skills(storage)
    for skill in skills:
        assert skill.description, f"Skill {skill.id} has empty description"
        assert skill.storage_path, f"Skill {skill.id} has empty storage_path"


def test_prebuilt_allowed_tools_match_tool_registry() -> None:
    """Every prebuilt allowed-tools entry must match a registered harness/server tool name."""
    registered = _load_registered_tool_names()
    violations: list[str] = []
    for skill_id, tools in _iter_prebuilt_seed_allowed_tools():
        for tool_name in tools:
            if tool_name not in registered:
                violations.append(f"{skill_id}: {tool_name}")
    assert not violations, (
        "Prebuilt SKILL.md allowed-tools must use registered tool names "
        "(see tool_layers.py + _tool_layer_bootstrap.py):\n" + "\n".join(f"  - {item}" for item in violations)
    )
