"""
[INPUT]
- .types::EvolutionApprovalPayload, EvolutionApplyError (POS: Evolution 审核域类型)
- myrm_agent_harness.api.skills::parse_skill_frontmatter, compute_content_hash (POS: SKILL.md frontmatter parser the skill loader uses; line-ending-insensitive content hash)
- myrm_agent_harness.infra.atomic_write::atomic_write (POS: crash-safe file replace)
[OUTPUT]
- skill_file_hash: hash of the SKILL.md on disk (the proposal's base)
- skill_file_differs, sync_store_from_disk: whether the SKILL.md holds other text than a copy, and bringing the evolution store's copy up to the file
- Full skill content apply (stale-base and loadability checks, atomic file write that is undone when the record or snapshot fails, SkillStore, agent fork bindings) and rollback (file system + SkillStore)
[POS]
Evolution 全量内容更新落盘与回滚（含 Copy-on-Write fork）。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.api.skills import SkillMetadataError, compute_content_hash, parse_skill_frontmatter
from myrm_agent_harness.infra.atomic_write import atomic_write

from .types import (
    REASON_SKILL_MD_UNLOADABLE,
    REASON_STALE_BASE,
    EvolutionApplyError,
    EvolutionApprovalPayload,
)

logger = logging.getLogger(__name__)


def _require_evolution_type(payload: EvolutionApprovalPayload) -> EvolutionType:
    """Parse the type before any side effect, so an unsupported one cannot leave a half-applied change."""
    try:
        return EvolutionType(payload.evolution_type)
    except ValueError as exc:
        raise EvolutionApplyError(f"Unsupported evolution type: {payload.evolution_type}") from exc


def _require_loadable_skill_md(content: str, skill_path: Path) -> None:
    """Refuse content the skill loader would skip, before any side effect (the loader parses with the same function)."""
    try:
        parse_skill_frontmatter(content, skill_path.parent.name)
    except SkillMetadataError as exc:
        raise EvolutionApplyError(f"Evolved SKILL.md cannot be loaded: {exc}", code=REASON_SKILL_MD_UNLOADABLE) from exc


def _read_skill_md(skill_path: Path) -> str | None:
    """The SKILL.md text (undecodable bytes are replaced, so the text and its hash are stable), None when unreadable."""
    try:
        return skill_path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def skill_file_hash(skill_path: Path) -> str | None:
    """Hash of the SKILL.md on disk, None when unreadable."""
    text = _read_skill_md(skill_path)
    return None if text is None else compute_content_hash(text)


def skill_file_differs(skill_path: str, content: str) -> bool:
    """Whether the SKILL.md at ``skill_path`` holds other text than ``content``; False where there is no file to compare."""
    if not skill_path:
        return False
    disk_hash = skill_file_hash(Path(skill_path))
    return disk_hash is not None and disk_hash != compute_content_hash(content)


async def sync_store_from_disk(store: SkillStore, skill: SkillRecord) -> bool:
    """Make the store's copy of a skill the SKILL.md on disk; True when the copy was out of date.

    The editor, a version rollback and the agent's skill tool change the file but not the store, and a proposal
    built from the store would diff against, and on approval overwrite, text the skill no longer has.
    ``updated_at`` stays as it was: the evolution cooldown counts from the last evolution, not from this copy.
    A file larger than the store takes is reported but not copied.
    """
    text = _read_skill_md(Path(skill.path)) if skill.path else None
    if text is None or compute_content_hash(text) == compute_content_hash(skill.content):
        return False
    if len(text) > SkillStore.MAX_SKILL_CONTENT_CHARS:
        logger.warning("SKILL.md of '%s' is too large for the evolution store; its copy there stays behind", skill.name)
        return True
    skill.content = text
    await store.save_skill(skill)
    return True


def _require_unchanged_base(payload: EvolutionApprovalPayload, base_path: Path, content_to_write: str) -> None:
    """Refuse a proposal whose skill file changed after it was created: writing it would silently drop those changes."""
    expected = payload.base_content_hash
    if expected is None:
        return
    # A file that already holds the content to write is a repeated apply, not a foreign change.
    if skill_file_hash(base_path) in (expected, compute_content_hash(content_to_write)):
        return
    raise EvolutionApplyError(
        "The skill file changed after this proposal was created; applying it would overwrite those changes.",
        code=REASON_STALE_BASE,
    )


def _restore_previous_file(path: Path, previous: bytes | None) -> None:
    """Undo the file write of an apply that failed afterwards: put the earlier bytes back, or remove the new file."""
    try:
        if previous is None:
            path.unlink(missing_ok=True)
            with suppress(OSError):  # a directory that still holds other files stays
                path.parent.rmdir()
        else:
            atomic_write(path, previous)
    except OSError:
        logger.exception("Could not restore %s after a failed apply; it still holds the evolved content", path)


async def apply_content_update(
    payload: EvolutionApprovalPayload,
    store: SkillStore,
    agent_id: str | None = None,
) -> None:
    """Write the evolved SKILL.md and record it; a failure after the file was written puts the earlier file back.

    A Copy-on-Write fork's identity goes onto the payload only once the apply succeeded, so a refused or
    failed apply leaves the proposal as it was reviewed.
    """
    evolution_type = _require_evolution_type(payload)
    base_path = Path(payload.skill_path)
    skill_path = base_path
    old_skill_id = payload.skill_id
    skill_id = old_skill_id
    skill_name = payload.skill_name
    existing = store.get_skill(old_skill_id)

    is_fork = False
    final_scope_agent_id = None

    if existing and existing.environment and "scope_agent_id" in existing.environment.custom_tags:
        owner_id = existing.environment.custom_tags["scope_agent_id"]
        if agent_id and owner_id != agent_id:
            is_fork = True
            skill_id = f"fork_{uuid.uuid4().hex[:8]}"
            skill_name = f"{skill_name}-fork"
            skill_path = base_path.parent.parent / skill_name / base_path.name
            existing = None
            final_scope_agent_id = agent_id
        else:
            final_scope_agent_id = owner_id
    elif evolution_type is EvolutionType.CAPTURED and agent_id:
        final_scope_agent_id = agent_id

    content_to_write = payload.evolved_content
    if final_scope_agent_id:

        def _inject_scope(match: re.Match[str]) -> str:
            fm = match.group(1)
            fm = re.sub(r"(?m)^scope_agent_id:\s*.*$", "", fm)
            return f"---\n{fm.strip()}\nscope_agent_id: {final_scope_agent_id}\n---"

        content_to_write = re.sub(
            r"^---\s*\n(.*?)\n---",
            _inject_scope,
            content_to_write,
            count=1,
            flags=re.DOTALL,
        )

    # Nothing below awaits until the write, so no other coroutine can change the file between the base
    # check and the write.
    _require_unchanged_base(payload, base_path, content_to_write)
    _require_loadable_skill_md(content_to_write, skill_path)

    previous = skill_path.read_bytes() if skill_path.is_file() else None
    atomic_write(skill_path, content_to_write.encode("utf-8"))

    lineage = SkillLineage(
        parent_id=skill_id,
        evolution_type=evolution_type,
        change_summary=payload.reason,
        created_at=datetime.now(),
        created_by="evolution_engine",
    )

    if existing:
        skill_record = existing
        skill_record.content = content_to_write
        skill_record.lineage = lineage
        skill_record.is_active = True
        if payload.eval_cases:
            skill_record.eval_cases = payload.eval_cases
        if final_scope_agent_id:
            if skill_record.environment is None:
                skill_record.environment = EnvironmentFingerprint()
            skill_record.environment.custom_tags["scope_agent_id"] = final_scope_agent_id
    else:
        env = EnvironmentFingerprint()
        if final_scope_agent_id:
            env.custom_tags["scope_agent_id"] = final_scope_agent_id

        skill_record = SkillRecord(
            skill_id=skill_id,
            name=skill_name,
            description="Auto-evolved skill",
            content=content_to_write,
            path=str(skill_path),
            lineage=lineage,
            is_active=True,
            environment=env,
            eval_cases=payload.eval_cases,
        )

    from app.services.skills.write_orchestrator import persist_skill_md_snapshot

    try:
        await store.save_skill(skill_record)
        await persist_skill_md_snapshot(
            skill_id,
            content_to_write,
            created_by="evolution_engine",
            sync_disk=False,
            disk_path=skill_path,
        )
    except Exception:
        _restore_previous_file(skill_path, previous)
        raise

    if is_fork:
        payload.skill_id = skill_id
        payload.skill_name = skill_name
        payload.skill_path = str(skill_path)
        payload.original_content = ""

    if is_fork and agent_id:
        try:
            from sqlalchemy.orm.attributes import flag_modified

            from app.database.connection import get_session
            from app.database.models import Agent

            async with get_session() as db:
                agent = await db.get(Agent, agent_id)
                if agent:
                    if agent.mounted_skill_ids and old_skill_id in agent.mounted_skill_ids:
                        new_mounted = [x for x in agent.mounted_skill_ids if x != old_skill_id]
                        agent.mounted_skill_ids = new_mounted
                        new_skill_ids = list(agent.skill_ids) if agent.skill_ids else []
                        if payload.skill_id not in new_skill_ids:
                            new_skill_ids.append(payload.skill_id)
                        agent.skill_ids = new_skill_ids
                    elif agent.skill_ids and old_skill_id in agent.skill_ids:
                        agent.skill_ids = [x if x != old_skill_id else payload.skill_id for x in agent.skill_ids]

                    flag_modified(agent, "mounted_skill_ids")
                    flag_modified(agent, "skill_ids")
                    await db.commit()
        except Exception as exc:
            logger.error(
                "Failed to update agent skill bindings during Copy-on-Write forking: %s",
                exc,
            )


async def rollback_content_update(payload: EvolutionApprovalPayload, store: SkillStore) -> None:
    evolution_type = _require_evolution_type(payload)
    skill_path = Path(payload.skill_path)

    if evolution_type is EvolutionType.DERIVED or not payload.original_content:
        # A fork's lineage points at the fork itself, so the skill id its agent was bound to before the
        # fork is not recoverable here: only the fork's files and record are removed, bindings stay as they are.
        if skill_path.exists():
            if skill_path.name == "SKILL.md":
                if skill_path.parent.name not in ["workspace", "skills", ""]:
                    shutil.rmtree(skill_path.parent, ignore_errors=True)
                else:
                    logger.warning(
                        "Skipping rmtree on unsafe path during rollback: %s",
                        skill_path.parent,
                    )
            else:
                os.remove(skill_path)
        try:
            await store.delete_skill(payload.skill_id)
        except Exception as exc:
            logger.warning("Failed to delete skill from DB during rollback: %s", exc)
    else:
        atomic_write(skill_path, payload.original_content.encode("utf-8"))

        lineage = SkillLineage(
            evolution_type=evolution_type,
            version=1,
            parent_id=None,
            change_summary="Rolled back",
            created_at=datetime.now(UTC),
            created_by="user",
        )
        skill_record = SkillRecord(
            skill_id=payload.skill_id,
            name=payload.skill_name,
            description="",
            content=payload.original_content,
            path=str(skill_path),
            lineage=lineage,
            is_active=True,
        )
        await store.save_skill(skill_record)
