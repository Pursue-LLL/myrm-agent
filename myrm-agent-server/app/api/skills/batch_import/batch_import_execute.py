"""批量导入确认落盘的核心执行逻辑（蓝绿原子写入 + DB 事务）。

[INPUT]
- app.api.skills._staging::SkillStagingManager (POS: 会话暂存管理，`_cleanup_expired_sessions_sync` 供后台任务)
- app.api.skills.batch_import_schemas::ConfirmImportRequest (POS: 确认导入请求体)
- app.api.skills.evolution.helpers::_get_skill_store (POS: 技能存储单例)
- myrm_agent_harness.agent.skills.evolution.core.types::EvolutionType / SkillLineage / SkillRecord
- myrm_agent_harness.agent.skills.packaging::is_evals_file / parse_evals_json
- myrm_agent_harness.agent.skills.optimization.security::SkillSecurityValidator
- myrm_agent_harness.agent.skills.optimization.config::SecurityConfig

[OUTPUT]
- execute_batch_import_confirm: 执行安全预检 + 蓝绿目录准备 + DB 批量事务 + 目录原子替换，返回 (imported_count, skipped_count, restored_eval_cases)

[POS]
批量导入确认路由的落盘执行器；路由层负责 HTTP 语义（校验/错误映射/后台任务），本模块负责无副作用的业务编排与磁盘/DB 原子性。
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import yaml
from fastapi import HTTPException
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.packaging import is_evals_file, parse_evals_json

from .batch_import_helpers import _build_batch_import_error_detail

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
    from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
        HermesImportedSkill,
    )
    from myrm_agent_harness.agent.skills.optimization.security import (
        SkillSecurityValidator,
    )

    from app.api.skills._staging import SkillStagingManager

    from .batch_import_schemas import ConfirmImportRequest

logger = logging.getLogger(__name__)


async def execute_batch_import_confirm(
    request: ConfirmImportRequest,
    store: SkillStore,
    staging_manager: SkillStagingManager,
    validator: SkillSecurityValidator,
    imported_skills: list[HermesImportedSkill],
) -> tuple[int, int, int]:
    """安全预检 → 蓝绿目录准备 → DB 批量写入 → 目录原子替换。

    - Phase 1: 逐项安全预检，命中恶意代码立即撤销本次导入。
    - Phase 2: 为每个技能构建 .tmp 目录，全保真写入文件、剥离 evals.json，
       replace 场景继承 DB 回归门禁快照与全部演化元数据（版本号/禁用/锁定/统计/陷阱）。
    - Phase 3: DB 单事务批量写入。
    - Phase 4: 全部 DB 提交成功后执行操作系统级蓝绿目录原子替换。
    - 任一阶段失败：清空本次 .tmp 目录、尽力恢复 old 目录并重新抛出。
    - 返回 (imported_count, skipped_count, restored_eval_cases)：restored_eval_cases 为
      本次导入最终保留的回归门禁用例总数（包内 evals.json 还原 + replace 场景从 DB 继承），
      与落盘门禁条数一致。
    """
    imported_count = 0
    skipped_count = 0
    restored_eval_cases = 0

    # Phase 1: 安全预检 (Defense-in-depth, 拦截恶意请求)
    for item in request.items:
        if item.resolution == "skip":
            continue

        try:
            skill_idx = int(item.virtual_id.split("_")[1])
            skill = imported_skills[skill_idx]
        except (IndexError, ValueError, KeyError) as e:
            raise HTTPException(
                status_code=400,
                detail=_build_batch_import_error_detail("非法的 virtual_id"),
            ) from e

        val_result = validator.validate_skill(
            f"---\nname: {item.name}\ndescription: {item.description}\n---\n{skill.content}"
        )
        if not val_result.passed:
            logger.warning(
                f"Skill {item.name} failed security scan during confirm: {val_result.issues}"
            )
            # 立即清理暂存区并阻断
            staging_manager.cleanup_session(request.session_id)
            raise HTTPException(
                status_code=400,
                detail=_build_batch_import_error_detail(
                    f"安全拦截: {item.name} 包含恶意代码 -> {val_result.issues}。本次导入已撤销。"
                ),
            )

    # Phase 2: 蓝绿目录准备与收集 (全保真原子写入)
    blue_green_tasks = []
    records_to_save = []
    try:
        for item in request.items:
            if item.resolution == "skip":
                skipped_count += 1
                continue

            skill_idx = int(item.virtual_id.split("_")[1])
            skill = imported_skills[skill_idx]

            skill_id = str(uuid.uuid4())
            name = item.name
            evolution_type = EvolutionType.FIX  # default
            parent_id = None

            if item.resolution == "replace" and item.existing_skill_id:
                # 覆盖：更新原技能
                skill_id = item.existing_skill_id
                evolution_type = EvolutionType.DERIVED
                parent_id = skill_id
            elif item.resolution == "rename_cow":
                name = f"{item.name}_copy"
                evolution_type = EvolutionType.DERIVED
                parent_id = item.existing_skill_id

            # 构建目标目录与临时目录
            skills_root = store.db_path.parent / "skills"
            skill_dir = skills_root / skill_id
            tmp_dir = skills_root / f".{skill_id}.{uuid.uuid4().hex}.tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            path = str(skill_dir / "SKILL.md")

            # replace 覆盖场景：继承 DB 中原回归门禁快照与全部演化元数据，
            # 避免 INSERT OR REPLACE 整行覆盖清空 eval_cases、回退版本号、重置统计/禁用/锁定状态
            # （与单包导入 force 覆盖语义一致：仅内容/描述/门禁更新，演化元数据保留）
            inherited: SkillRecord | None = None
            inherited_eval_cases: list[dict[str, object]] = []
            if item.resolution == "replace" and item.existing_skill_id:
                inherited = store.get_skill(item.existing_skill_id)
                if inherited is not None:
                    inherited_eval_cases = inherited.eval_cases

            if inherited is not None:
                record = SkillRecord(
                    skill_id=skill_id,
                    name=name,
                    description=item.description,
                    content=skill.content,
                    path=path,
                    lineage=SkillLineage(
                        evolution_type=evolution_type,
                        version=inherited.lineage.version,
                        parent_id=parent_id,
                        change_summary="Migrated via Hermes Batch Import",
                        created_by=inherited.lineage.created_by,
                        created_at=inherited.lineage.created_at,
                    ),
                    metrics=inherited.metrics,
                    environment=inherited.environment,
                    created_at=inherited.created_at,
                    updated_at=datetime.now(),
                    is_active=inherited.is_active,
                    evolution_locked=inherited.evolution_locked,
                    traps=inherited.traps,
                    verification_steps=inherited.verification_steps,
                )
            else:
                record = SkillRecord(
                    skill_id=skill_id,
                    name=name,
                    description=item.description,
                    content=skill.content,
                    path=path,
                    lineage=SkillLineage(
                        evolution_type=evolution_type,
                        version=1,
                        parent_id=parent_id,
                        change_summary="Migrated via Hermes Batch Import",
                        created_by="human",
                    ),
                )

            # 剥离包内保留文件 evals.json 并还原回归门禁快照
            # 与单包导入 unpack_and_register 语义一致：仅第一个有效者胜出；
            # 包内无 evals.json 时 replace 继承 DB 门禁，同样计入反馈计数，
            # 保证 restored_eval_cases 与最终落盘门禁条数一致
            restored = False
            for rel_path, file_content in list(skill.files.items()):
                if not is_evals_file(rel_path):
                    continue
                parsed = parse_evals_json(file_content)
                if parsed is None:
                    logger.warning("Skill %s: ignoring invalid %s", name, rel_path)
                elif not restored:
                    record.eval_cases = parsed
                    restored = True
                    restored_eval_cases += len(parsed)
                skill.files.pop(rel_path)

            if not restored:
                record.eval_cases = inherited_eval_cases
                restored_eval_cases += len(inherited_eval_cases)

            records_to_save.append(record)

            # 多文件全保真原子写入：为所有 file 生成到 .tmp 目录
            for rel_path, file_content in skill.files.items():
                target_path = tmp_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                if rel_path == "SKILL.md":
                    # YAML 深度合并，保留其他 Hermes 元数据 (如 dependencies, version 等)
                    new_metadata = dict(skill.metadata)
                    new_metadata["name"] = name
                    new_metadata["description"] = item.description
                    # 生成合法 frontmatter
                    fm_yaml = yaml.safe_dump(
                        new_metadata, allow_unicode=True, sort_keys=False
                    ).strip()
                    file_content = f"---\n{fm_yaml}\n---\n{skill.content}".encode(
                        "utf-8"
                    )

                with open(target_path, "wb") as f:
                    f.write(file_content)

            # 记录蓝绿切换任务
            blue_green_tasks.append(
                {
                    "skill_dir": skill_dir,
                    "tmp_dir": tmp_dir,
                    "old_dir": skills_root / f".{skill_id}.{uuid.uuid4().hex}.old",
                }
            )

            imported_count += 1

        # Phase 3: DB 批量写入，保证绝对的跨技能事务原子性
        if records_to_save:
            # Requires `save_skills_batch` on SkillStore which handles executemany in a single transaction
            if hasattr(store, "save_skills_batch"):
                await store.save_skills_batch(records_to_save)
            else:
                # Fallback for extreme cases, though we added save_skills_batch
                for r in records_to_save:
                    await store.save_skill(r)

        # Phase 4: 全部 DB 提交成功后，在操作系统底层执行蓝绿目录原子替换
        for task in blue_green_tasks:
            s_dir = task["skill_dir"]
            t_dir = task["tmp_dir"]
            o_dir = task["old_dir"]

            # 1. 瞬间将老技能移走 (如果存在)
            if s_dir.exists():
                os.rename(s_dir, o_dir)
            # 2. 瞬间让新技能顶替
            os.rename(t_dir, s_dir)
            # 3. 异步/安全删除老废弃技能 (防孤儿残留)
            if o_dir.exists():
                try:
                    shutil.rmtree(o_dir, ignore_errors=True)
                except Exception:
                    pass

    except Exception as e:
        # 回滚：此时 DB 未受污染（如果 save_skills_batch 报错了，整个事务已被 rollback）
        # 全量清空本次产生的所有 tmp 目录，并尝试恢复 old（极端防卫）
        for task in blue_green_tasks:
            try:
                if task["tmp_dir"].exists():
                    shutil.rmtree(task["tmp_dir"], ignore_errors=True)
                # 极端情况下若 rename(tmp, s) 失败，尝试把 old 恢复回去
                if not task["skill_dir"].exists() and task["old_dir"].exists():
                    os.rename(task["old_dir"], task["skill_dir"])
            except Exception:
                pass
        staging_manager.cleanup_session(request.session_id)
        raise e

    return imported_count, skipped_count, restored_eval_cases
