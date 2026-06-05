import os

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillMetrics,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.skills.evolution.helpers import _get_skill_store_db_path
from app.core.skills.loader import create_skill_backend


@pytest.fixture
def temp_workspace(tmp_path):
    # Setup a temporary workspace
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Set environment variable so _get_skill_store_db_path uses this
    os.environ["MYRM_DATA_DIR"] = str(workspace)
    yield workspace
    if "MYRM_DATA_DIR" in os.environ:
        del os.environ["MYRM_DATA_DIR"]


@pytest.mark.asyncio
async def test_quarantine_aware_integration(temp_workspace):
    """
    真实集成测试：
    1. 在文件系统中创建一个技能
    2. 在 SQLite 数据库中记录该技能，并将其标记为 is_active=False
    3. 调用业务层的 create_skill_backend
    4. 验证 list_skills() 是否成功过滤掉了被隔离的技能
    """
    from datetime import UTC, datetime

    # 1. 设置存储
    storage = LocalStorageBackend(str(temp_workspace))

    # 2. 在文件系统中创建预构建技能
    skills_prefix = "skills/prebuilt"
    skill_id = "test_quarantined_skill"
    skill_dir = f"{skills_prefix}/{skill_id}"

    await storage.write_text(f"{skill_dir}/SKILL.md", "---\ndescription: test\n---\n# Test Skill")
    await storage.write_text(
        f"{skill_dir}/metadata.json",
        '{"name": "test_quarantined_skill", "description": "test"}',
    )

    # 创建一个正常的技能
    normal_skill_id = "test_normal_skill"
    normal_skill_dir = f"{skills_prefix}/{normal_skill_id}"
    await storage.write_text(f"{normal_skill_dir}/SKILL.md", "---\ndescription: normal\n---\n# Normal Skill")
    await storage.write_text(
        f"{normal_skill_dir}/metadata.json",
        '{"name": "test_normal_skill", "description": "normal"}',
    )

    # 3. 在 SQLite 数据库中记录技能状态
    db_path = _get_skill_store_db_path()
    store = SkillStore(db_path=db_path)

    try:
        now = datetime.now(UTC)

        # 隔离的技能 (is_active=False)
        quarantined_record = SkillRecord(
            skill_id=skill_id,
            name=skill_id,
            description="test",
            content="# Test Skill",
            path=f"{skill_dir}/SKILL.md",
            lineage=SkillLineage(
                evolution_type=EvolutionType.CAPTURED,
                version=1,
                parent_id=None,
                change_summary="init",
                created_at=now,
                created_by="test",
            ),
            metrics=SkillMetrics(),
            created_at=now,
            updated_at=now,
            is_active=False,  # <--- 核心：标记为隔离
            evolution_locked=False,
        )
        await store.save_skill(quarantined_record)

        # 正常的技能 (is_active=True)
        normal_record = SkillRecord(
            skill_id=normal_skill_id,
            name=normal_skill_id,
            description="normal",
            content="# Normal Skill",
            path=f"{normal_skill_dir}/SKILL.md",
            lineage=SkillLineage(
                evolution_type=EvolutionType.CAPTURED,
                version=1,
                parent_id=None,
                change_summary="init",
                created_at=now,
                created_by="test",
            ),
            metrics=SkillMetrics(),
            created_at=now,
            updated_at=now,
            is_active=True,  # <--- 核心：标记为正常
            evolution_locked=False,
        )
        await store.save_skill(normal_record)

    finally:
        store.close()

    # 4. 调用业务层加载器
    backend = await create_skill_backend(storage=storage)

    # 5. 验证过滤效果
    skills = await backend.list_skills()

    skill_names = [s.name for s in skills]

    # 正常技能应该在列表中
    assert normal_skill_id in skill_names

    # 被隔离的技能应该被过滤掉
    assert skill_id not in skill_names

    print(f"\n✅ 集成测试通过：成功过滤隔离技能 {skill_id}，保留正常技能 {normal_skill_id}")
