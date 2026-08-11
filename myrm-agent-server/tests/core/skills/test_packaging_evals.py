"""Tests for skill package evals.json export/import round-trip."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.packaging import EVALS_FILE, parse_evals_json, serialize_eval_cases

from app.core.skills.models import Skill, SkillType
from app.core.skills.packaging import PackageResult, SkillPackagingService

EVAL_CASES = [
    {
        "message": "sum the numbers 1 and 2",
        "expected_tools": ["code_interpreter"],
        "require_all": True,
        "metadata": {"severity": "high"},
    }
]

SKILL_MD = """---
name: demo_skill
description: Demo skill
version: 1.0.0
---

# Demo Skill
"""


class _FakeSkillsService:
    """Minimal SkillsService stub exercising the packaging facade."""

    def __init__(
        self,
        skill: Skill,
        files: dict[str, bytes],
        existing: list[Skill] | None = None,
    ) -> None:
        self._skill = skill
        self._files = files
        self._existing = existing if existing is not None else [skill]
        self.registered_files: dict[str, bytes] | None = None

    async def get_skill(self, skill_id: str) -> Skill | None:
        for skill in self._existing:
            if skill.id == skill_id:
                return skill
        return None

    async def list_skill_files(self, skill_id: str) -> list[str]:
        return list(self._files)

    async def get_skill_file(self, skill_id: str, file_path: str) -> bytes | None:
        return self._files.get(file_path)

    async def list_skills(self) -> list[Skill]:
        return list(self._existing)

    async def create_skill(
        self,
        name: str,
        description: str,
        skill_type: SkillType,
        files: dict[str, bytes],
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        self.registered_files = dict(files)
        skill = Skill(
            id=name,
            type=skill_type,
            name=name,
            description=description,
            storage_path=f"skills/prebuilt/{name}",
        )
        self._existing.append(skill)
        return skill


def _make_record(skill_id: str, eval_cases: list[dict]) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name=skill_id,
        description="desc",
        content=SKILL_MD,
        path="skills/prebuilt/demo_skill/SKILL.md",
        lineage=SkillLineage(
            evolution_type=EvolutionType.DERIVED,
            version=3,
            change_summary="v3",
            created_by="test",
        ),
        eval_cases=eval_cases,
        is_active=True,
        environment=EnvironmentFingerprint(),
    )


@pytest.fixture
def packaging_service() -> SkillPackagingService:
    skill = Skill(
        id="demo_skill",
        type=SkillType.PREBUILT,
        name="demo_skill",
        description="Demo skill",
        storage_path="skills/prebuilt/demo_skill",
        version="1.0.0",
    )
    files = {
        "SKILL.md": SKILL_MD.encode("utf-8"),
        "helper.py": b"def run():\n    return 42\n",
    }
    return SkillPackagingService(skills_svc=_FakeSkillsService(skill, files))


async def test_export_includes_evals_json(
    packaging_service: SkillPackagingService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _make_record("demo_skill", EVAL_CASES)
    monkeypatch.setattr(
        "app.core.skills.packaging._load_evolution_record",
        lambda skill_name: record,
    )

    result: PackageResult = await packaging_service.package_skill("demo_skill")

    assert result.success
    assert result.eval_cases_count == 1
    assert result.filename == "demo_skill_v3.zip"
    assert result.zip_content is not None

    with zipfile.ZipFile(io.BytesIO(result.zip_content), "r") as zf:
        names = zf.namelist()
        assert "demo_skill/SKILL.md" in names
        assert f"demo_skill/{EVALS_FILE}" in names
        evals_content = zf.read(f"demo_skill/{EVALS_FILE}").decode("utf-8")
        skill_md = zf.read("demo_skill/SKILL.md").decode("utf-8")

    # version 已同步为 lineage.version=3
    assert "version: 3" in skill_md
    # evals.json 内容可还原
    assert parse_evals_json(evals_content) == EVAL_CASES


async def test_export_syncs_frontmatter_version_when_present(
    packaging_service: SkillPackagingService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _make_record("demo_skill", [])
    monkeypatch.setattr(
        "app.core.skills.packaging._load_evolution_record",
        lambda skill_name: record,
    )

    result: PackageResult = await packaging_service.package_skill("demo_skill")

    assert result.success
    assert result.eval_cases_count == 0
    assert result.filename == "demo_skill_v3.zip"
    assert result.zip_content is not None
    with zipfile.ZipFile(io.BytesIO(result.zip_content), "r") as zf:
        skill_md = zf.read("demo_skill/SKILL.md").decode("utf-8")
        # 无 eval_cases 时不写入 evals.json
        assert f"demo_skill/{EVALS_FILE}" not in zf.namelist()
    assert "version: 3" in skill_md


async def test_export_without_evolution_record_keeps_default_version(
    packaging_service: SkillPackagingService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.skills.packaging._load_evolution_record",
        lambda skill_name: None,
    )

    result: PackageResult = await packaging_service.package_skill("demo_skill")

    assert result.success
    assert result.eval_cases_count == 0
    assert result.filename == "demo_skill_v1.0.0.zip"
    assert result.zip_content is not None
    with zipfile.ZipFile(io.BytesIO(result.zip_content), "r") as zf:
        assert f"demo_skill/{EVALS_FILE}" not in zf.namelist()


def _build_zip_with_evals(eval_cases: list[dict] | None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo_skill/SKILL.md", SKILL_MD)
        zf.writestr("demo_skill/helper.py", "def run():\n    return 42\n")
        if eval_cases is not None:
            zf.writestr("demo_skill/evals.json", serialize_eval_cases("demo_skill", eval_cases))
    return buffer.getvalue()


async def test_export_ignores_user_evals_json_file(
    packaging_service: SkillPackagingService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """技能目录中手写 evals.json 不参与打包，由快照逻辑生成包内 evals.json。"""
    record = _make_record("demo_skill", EVAL_CASES)
    monkeypatch.setattr(
        "app.core.skills.packaging._load_evolution_record",
        lambda skill_name: record,
    )
    packaging_service._skills_svc._files["evals.json"] = b'{"schema_version":999,"evals":[]}'

    result: PackageResult = await packaging_service.package_skill("demo_skill")

    assert result.success
    assert result.zip_content is not None
    with zipfile.ZipFile(io.BytesIO(result.zip_content), "r") as zf:
        evals_content = zf.read(f"demo_skill/{EVALS_FILE}").decode("utf-8")
    # 包内 evals.json 为生成快照，非手写文件内容
    assert "schema_version" in evals_content
    assert parse_evals_json(evals_content) == EVAL_CASES


async def test_import_strips_all_evals_json_locations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """多层级的 evals.json 全部剥离，仅第一个有效者被还原，且不写入技能目录。"""
    from myrm_agent_harness.agent.skills.evolution import SkillStore

    db_path = tmp_path / "skills.db"

    def _fresh_store() -> SkillStore:
        return SkillStore(db_path=db_path)

    monkeypatch.setattr(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        _fresh_store,
    )
    fake_svc = _FakeSkillsService(
        Skill(
            id="demo_skill",
            type=SkillType.PREBUILT,
            name="demo_skill",
            description="Demo skill",
            storage_path="skills/prebuilt/demo_skill",
        ),
        files={},
        existing=[],
    )
    service = SkillPackagingService(skills_svc=fake_svc)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo_skill/SKILL.md", SKILL_MD)
        zf.writestr("demo_skill/evals.json", serialize_eval_cases("demo_skill", EVAL_CASES))
        zf.writestr("demo_skill/nested/evals.json", serialize_eval_cases("demo_skill", []))
    result = await service.unpack_and_register(buffer.getvalue())

    assert result.success
    assert result.restored_eval_cases == 1
    # 两个 evals.json 均未写入技能目录
    assert fake_svc.registered_files is not None
    assert "evals.json" not in fake_svc.registered_files
    assert "nested/evals.json" not in fake_svc.registered_files

    verify_store = _fresh_store()
    try:
        saved = verify_store.get_skill_by_name_version("demo_skill")
    finally:
        verify_store.close()
    assert saved is not None
    assert saved.eval_cases == EVAL_CASES


async def test_import_restores_eval_cases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from myrm_agent_harness.agent.skills.evolution import SkillStore

    db_path = tmp_path / "skills.db"

    def _fresh_store() -> SkillStore:
        return SkillStore(db_path=db_path)

    monkeypatch.setattr(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        _fresh_store,
    )
    fake_svc = _FakeSkillsService(
        Skill(
            id="demo_skill",
            type=SkillType.PREBUILT,
            name="demo_skill",
            description="Demo skill",
            storage_path="skills/prebuilt/demo_skill",
        ),
        files={},
        existing=[],
    )
    service = SkillPackagingService(skills_svc=fake_svc)
    zip_bytes = _build_zip_with_evals(EVAL_CASES)
    result = await service.unpack_and_register(zip_bytes)

    assert result.success
    assert result.skill_id == "demo_skill"
    assert result.restored_eval_cases == 1

    verify_store = _fresh_store()
    try:
        saved = verify_store.get_skill_by_name_version("demo_skill")
    finally:
        verify_store.close()
    assert saved is not None
    assert saved.eval_cases == EVAL_CASES

    # evals.json 未写入技能存储目录
    assert fake_svc.registered_files is not None
    assert "evals.json" not in fake_svc.registered_files


async def test_import_without_evals_keeps_no_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from myrm_agent_harness.agent.skills.evolution import SkillStore

    db_path = tmp_path / "skills.db"

    def _fresh_store() -> SkillStore:
        return SkillStore(db_path=db_path)

    monkeypatch.setattr(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        _fresh_store,
    )
    fake_svc = _FakeSkillsService(
        Skill(
            id="demo_skill",
            type=SkillType.PREBUILT,
            name="demo_skill",
            description="Demo skill",
            storage_path="skills/prebuilt/demo_skill",
        ),
        files={},
        existing=[],
    )
    service = SkillPackagingService(skills_svc=fake_svc)
    zip_bytes = _build_zip_with_evals(None)
    result = await service.unpack_and_register(zip_bytes)

    assert result.success
    assert result.restored_eval_cases == 0

    verify_store = _fresh_store()
    try:
        assert verify_store.get_skill_by_name_version("demo_skill") is None
    finally:
        verify_store.close()


async def test_import_with_invalid_evals_ignored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from myrm_agent_harness.agent.skills.evolution import SkillStore

    db_path = tmp_path / "skills.db"

    def _fresh_store() -> SkillStore:
        return SkillStore(db_path=db_path)

    monkeypatch.setattr(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        _fresh_store,
    )
    fake_svc = _FakeSkillsService(
        Skill(
            id="demo_skill",
            type=SkillType.PREBUILT,
            name="demo_skill",
            description="Demo skill",
            storage_path="skills/prebuilt/demo_skill",
        ),
        files={},
        existing=[],
    )
    service = SkillPackagingService(skills_svc=fake_svc)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo_skill/SKILL.md", SKILL_MD)
        zf.writestr("demo_skill/evals.json", "{invalid json")
    result = await service.unpack_and_register(buffer.getvalue())

    assert result.success
    assert result.restored_eval_cases == 0

    verify_store = _fresh_store()
    try:
        assert verify_store.get_skill_by_name_version("demo_skill") is None
    finally:
        verify_store.close()


def test_sync_skill_md_version_injects_and_replaces() -> None:
    from app.core.skills.packaging import _sync_skill_md_version

    # 替换已有 version
    assert _sync_skill_md_version(SKILL_MD, "7") == SKILL_MD.replace("version: 1.0.0", "version: 7")

    # 无 frontmatter 不修改
    plain = "# No frontmatter\n"
    assert _sync_skill_md_version(plain, "7") == plain

    # 无 version 字段时插入
    no_version = "---\nname: x\n---\n# X\n"
    synced = _sync_skill_md_version(no_version, "7")
    assert "version: 7" in synced
    assert synced.index("version: 7") < synced.index("---", 1)


async def test_evals_json_auto_redaction(
    packaging_service: SkillPackagingService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """eval_cases 中含密钥时导出自动脱敏，不阻塞打包。"""
    sensitive_cases = [
        {
            "message": "use the api key sk-abcdef1234567890 in the config",
            "expected_tools": ["code_interpreter"],
        }
    ]
    record = _make_record("demo_skill", sensitive_cases)
    monkeypatch.setattr(
        "app.core.skills.packaging._load_evolution_record",
        lambda skill_name: record,
    )

    result: PackageResult = await packaging_service.package_skill("demo_skill")

    assert result.success
    assert result.eval_cases_count == 1
    assert result.zip_content is not None
    with zipfile.ZipFile(io.BytesIO(result.zip_content), "r") as zf:
        evals_content = zf.read(f"demo_skill/{EVALS_FILE}").decode("utf-8")
    assert "sk-abcdef1234567890" not in evals_content
    assert "<REDACTED" in evals_content
