"""
[INPUT]
- app.services.skills.evolution_review_types::EvolutionApprovalPayload
[OUTPUT]
- Full skill content apply + rollback (file system + SkillStore + agent fork bindings)
[POS]
Evolution 全量内容更新落盘与回滚（含 Copy-on-Write fork）。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

from app.database.dto import AgentUpdate
from app.services.skills.evolution_review_types import EvolutionApprovalPayload

logger = logging.getLogger(__name__)


async def apply_content_update(
    payload: EvolutionApprovalPayload,
    store: SkillStore,
    agent_id: str | None = None,
) -> None:
    skill_path = Path(payload.skill_path)
    existing = store.get_skill(payload.skill_id)

    is_fork = False
    old_skill_id = payload.skill_id
    final_scope_agent_id = None

    if existing and existing.environment and "scope_agent_id" in existing.environment.custom_tags:
        owner_id = existing.environment.custom_tags["scope_agent_id"]
        if agent_id and owner_id != agent_id:
            is_fork = True
            payload.skill_id = f"fork_{uuid.uuid4().hex[:8]}"
            payload.skill_name = f"{payload.skill_name}-fork"
            orig_path = Path(payload.skill_path)
            skill_path = orig_path.parent.parent / payload.skill_name / orig_path.name
            payload.skill_path = str(skill_path)
            payload.original_content = ""
            existing = None
            final_scope_agent_id = agent_id
        else:
            final_scope_agent_id = owner_id
    elif payload.evolution_type in (EvolutionType.CAPTURED.value, EvolutionType.SLICE_EXTRACTION.value) and agent_id:
        final_scope_agent_id = agent_id

    content_to_write = payload.evolved_content
    if final_scope_agent_id:

        def _inject_scope(match: re.Match[str]) -> str:
            fm = match.group(1)
            fm = re.sub(r"(?m)^scope_agent_id:\s*.*$", "", fm)
            return f"---\n{fm.strip()}\nscope_agent_id: {final_scope_agent_id}\n---"

        content_to_write = re.sub(r"^---\s*\n(.*?)\n---", _inject_scope, content_to_write, count=1, flags=re.DOTALL)

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=skill_path.parent, prefix="skill_evolve_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            file_obj.write(content_to_write)
        os.replace(temp_path, skill_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    lineage = SkillLineage(
        parent_id=payload.skill_id,
        evolution_type=EvolutionType(payload.evolution_type),
        change_summary=payload.reason,
        created_at=datetime.now(),
        created_by="evolution_engine",
    )

    if existing:
        skill_record = existing
        skill_record.content = payload.evolved_content
        skill_record.lineage = lineage
        skill_record.is_active = True
        if final_scope_agent_id:
            if skill_record.environment is None:
                skill_record.environment = EnvironmentFingerprint()
            skill_record.environment.custom_tags["scope_agent_id"] = final_scope_agent_id
    else:
        env = EnvironmentFingerprint()
        if final_scope_agent_id:
            env.custom_tags["scope_agent_id"] = final_scope_agent_id

        skill_record = SkillRecord(
            skill_id=payload.skill_id,
            name=payload.skill_name,
            description="Auto-evolved skill",
            content=payload.evolved_content,
            path=str(skill_path),
            lineage=lineage,
            is_active=True,
            environment=env,
        )

    await store.save_skill(skill_record)

    try:
        from app.services.skill_optimization.bootstrap import get_skill_optimization_storage as get_storage
        from app.services.skill_optimization.skill_version_sync import persist_skill_version

        opt_storage = get_storage()
        await persist_skill_version(
            opt_storage,
            payload.skill_id,
            content_to_write,
            created_by="evolution_engine",
            disk_path=skill_path,
        )
    except Exception as exc:
        logger.warning(
            "Failed to persist skill version snapshot for %s: %s",
            payload.skill_id,
            exc,
        )

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
            logger.error("Failed to update agent skill bindings during Copy-on-Write forking: %s", exc)


async def rollback_content_update(payload: EvolutionApprovalPayload, store: SkillStore) -> None:
    skill_path = Path(payload.skill_path)

    if payload.evolution_type == EvolutionType.DERIVED.value or not payload.original_content:
        fork_skill = store.get_skill(payload.skill_id)
        owner_id = None
        parent_id = None
        if fork_skill:
            if fork_skill.environment and "scope_agent_id" in fork_skill.environment.custom_tags:
                owner_id = fork_skill.environment.custom_tags["scope_agent_id"]
            if fork_skill.lineage:
                parent_id = fork_skill.lineage.parent_id

        if skill_path.exists():
            if skill_path.name == "SKILL.md":
                if skill_path.parent.name not in ["workspace", "skills", ""]:
                    shutil.rmtree(skill_path.parent, ignore_errors=True)
                else:
                    logger.warning("Skipping rmtree on unsafe path during rollback: %s", skill_path.parent)
            else:
                os.remove(skill_path)
        try:
            await store.delete_skill(payload.skill_id)
        except Exception as exc:
            logger.warning("Failed to delete skill from DB during rollback: %s", exc)

        if owner_id and parent_id:
            try:
                from app.services.agent.agent_service import agent_service

                agent = await agent_service.get_agent(owner_id)
                if agent:
                    mounted_ids = agent.mounted_skill_ids or []
                    skill_ids = agent.skill_ids or []
                    update_needed = False

                    if payload.skill_id in skill_ids:
                        skill_ids = [x for x in skill_ids if x != payload.skill_id]

                        parent_skill = store.get_skill(parent_id)
                        parent_owner_id = None
                        if parent_skill and parent_skill.environment and "scope_agent_id" in parent_skill.environment.custom_tags:
                            parent_owner_id = parent_skill.environment.custom_tags["scope_agent_id"]

                        if parent_owner_id and parent_owner_id != owner_id:
                            if parent_id not in mounted_ids:
                                mounted_ids.append(parent_id)
                        else:
                            if parent_id not in skill_ids:
                                skill_ids.append(parent_id)

                        update_needed = True

                    if update_needed:
                        await agent_service.update_agent(
                            owner_id, AgentUpdate(mounted_skill_ids=mounted_ids, skill_ids=skill_ids)
                        )
            except Exception as exc:
                logger.error("Failed to restore parent mount during rollback: %s", exc)
    else:
        fd, temp_path = tempfile.mkstemp(dir=skill_path.parent, prefix="skill_rollback_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
                file_obj.write(payload.original_content)
            os.replace(temp_path, skill_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        lineage = SkillLineage(
            evolution_type=EvolutionType(payload.evolution_type),
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
