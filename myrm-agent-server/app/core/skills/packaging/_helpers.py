"""包装模块内部辅助函数（供 packaging 门面复用）。

[INPUT]
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: 进化 SQLite 入口)

[OUTPUT]
- _load_evolution_record: 按技能名加载活动演化记录（best-effort）
- _sync_skill_md_version: 同步 SKILL.md frontmatter version 与 lineage 版本一致

[POS]
skills/packaging 门面内部的纯辅助函数；无业务状态，仅被 __init__ 复用。
"""

import logging

from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord

logger = logging.getLogger(__name__)


def _load_evolution_record(skill_name: str) -> SkillRecord | None:
    """Best-effort load of the active evolution record for a skill name."""
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        try:
            return store.get_skill_by_name_version(skill_name)
        finally:
            store.close()
    except Exception as exc:
        logger.debug("Evolution record lookup failed for %s: %s", skill_name, exc)
        return None


def _sync_skill_md_version(content: str, version: str) -> str:
    """Sync SKILL.md frontmatter version so exported package reflects real lineage version."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return content
    fm_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return content
    for i in range(1, fm_end):
        stripped = lines[i].strip()
        if stripped.startswith("version:"):
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = f"{indent}version: {version}"
            return "\n".join(lines)
    lines.insert(fm_end, f"version: {version}")
    return "\n".join(lines)
