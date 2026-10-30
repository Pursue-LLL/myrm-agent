"""SkillStore keeps a skill's eval_cases through save, reopen and batch save."""

import copy
from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore


@pytest.fixture
def temp_db_path(tmp_path: Path):
    return tmp_path / "test_skills.db"


@pytest.mark.asyncio
async def test_eval_cases_persistence(temp_db_path):
    """Verify eval_cases survive a save -> close -> reopen -> get cycle."""
    eval_cases = [
        {"sandbox_assertions": [{"type": "code_contains", "target": "nginx"}]},
        {"expected_tools": ["shell"]},
    ]
    record = SkillRecord(
        skill_id="eval_persist_1",
        name="eval-persist-skill",
        description="Test eval_cases persistence",
        content="install nginx",
        path="skills/eval_persist.md",
        lineage=SkillLineage(
            evolution_type=EvolutionType.CAPTURED,
            version=1,
        ),
        eval_cases=eval_cases,
    )

    store = SkillStore(db_path=temp_db_path)
    await store.save_skill(record)
    store.close()

    store2 = SkillStore(db_path=temp_db_path)
    loaded = store2.get_skill("eval_persist_1")
    assert loaded is not None
    assert loaded.eval_cases == eval_cases
    assert loaded.eval_cases[0]["sandbox_assertions"][0]["target"] == "nginx"
    assert loaded.eval_cases[1]["expected_tools"] == ["shell"]
    store2.close()


@pytest.mark.asyncio
async def test_eval_cases_empty_list_persistence(temp_db_path):
    """Verify eval_cases=[] persists correctly (default case)."""
    record = SkillRecord(
        skill_id="eval_empty_1",
        name="no-eval-skill",
        description="Skill without eval_cases",
        content="just content",
        path="skills/no_eval.md",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
    )

    store = SkillStore(db_path=temp_db_path)
    await store.save_skill(record)
    store.close()

    store2 = SkillStore(db_path=temp_db_path)
    loaded = store2.get_skill("eval_empty_1")
    assert loaded is not None
    assert loaded.eval_cases == []
    store2.close()


@pytest.mark.asyncio
async def test_eval_cases_unicode_persistence(temp_db_path):
    """Verify eval_cases with Unicode content persist correctly."""
    eval_cases = [
        {"sandbox_assertions": [{"type": "code_contains", "target": "安装nginx"}]},
        {"sandbox_assertions": [{"type": "code_not_contains", "target": "删除数据库"}]},
    ]
    record = SkillRecord(
        skill_id="eval_unicode_1",
        name="unicode-skill",
        description="Skill with Unicode eval_cases",
        content="安装 nginx 服务器",
        path="skills/unicode.md",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
        eval_cases=eval_cases,
    )

    store = SkillStore(db_path=temp_db_path)
    await store.save_skill(record)
    store.close()

    store2 = SkillStore(db_path=temp_db_path)
    loaded = store2.get_skill("eval_unicode_1")
    assert loaded is not None
    assert loaded.eval_cases == eval_cases
    assert loaded.eval_cases[0]["sandbox_assertions"][0]["target"] == "安装nginx"
    store2.close()


@pytest.mark.asyncio
async def test_eval_cases_batch_save_persistence(temp_db_path):
    """Verify eval_cases persist correctly through batch save."""
    base_record = SkillRecord(
        skill_id="batch_eval_0",
        name="batch-eval-0",
        description="Batch test",
        content="content",
        path="skills/batch.md",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
        eval_cases=[{"sandbox_assertions": [{"type": "ast_valid"}]}],
    )

    records = []
    for i in range(3):
        r = copy.deepcopy(base_record)
        r.skill_id = f"batch_eval_{i}"
        r.name = f"batch-eval-{i}"
        r.eval_cases = [{"sandbox_assertions": [{"type": "code_contains", "target": f"key_{i}"}]}]
        records.append(r)

    store = SkillStore(db_path=temp_db_path)
    await store.save_skills_batch(records)
    store.close()

    store2 = SkillStore(db_path=temp_db_path)
    for i in range(3):
        loaded = store2.get_skill(f"batch_eval_{i}")
        assert loaded is not None
        assert loaded.eval_cases[0]["sandbox_assertions"][0]["target"] == f"key_{i}"
    store2.close()
