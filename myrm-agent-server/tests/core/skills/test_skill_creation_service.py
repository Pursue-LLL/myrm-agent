"""Tests for SkillCreationService."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.skills.creation.service import SkillCreationService


@pytest.fixture
def service(tmp_path: Path) -> SkillCreationService:
    return SkillCreationService(base_path=tmp_path)


@pytest.mark.asyncio
async def test_write_resource_python_ast_validation_success(service: SkillCreationService, tmp_path: Path) -> None:
    # Create skill dir
    skill_dir = tmp_path / "valid-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: valid-skill\ndescription: demo\n---\n", encoding="utf-8")

    # Valid python resource
    res = await service.write_resource(
        skill_name="valid-skill",
        resource_path="scripts/helper.py",
        content="def calculate(a: int, b: int) -> int:\n    return a + b\n",
    )
    assert res.success is True
    assert (skill_dir / "scripts" / "helper.py").exists()


@pytest.mark.asyncio
async def test_write_resource_python_ast_validation_failure(service: SkillCreationService, tmp_path: Path) -> None:
    # Create skill dir
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: broken-skill\ndescription: demo\n---\n", encoding="utf-8")

    # Broken python resource
    res = await service.write_resource(
        skill_name="broken-skill",
        resource_path="scripts/broken.py",
        content="def bad_syntax(\n",
    )
    assert res.success is False
    assert "Python syntax error" in (res.error or "")
    assert not (skill_dir / "scripts" / "broken.py").exists()


@pytest.mark.asyncio
async def test_write_resource_non_python_unaffected(service: SkillCreationService, tmp_path: Path) -> None:
    # Create skill dir
    skill_dir = tmp_path / "text-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: text-skill\ndescription: demo\n---\n", encoding="utf-8")

    # Arbitrary text resource (e.g. template or txt)
    res = await service.write_resource(
        skill_name="text-skill",
        resource_path="templates/prompt.txt",
        content="This is not python code: def foo(",
    )
    assert res.success is True
    assert (skill_dir / "templates" / "prompt.txt").exists()


@pytest.mark.asyncio
async def test_write_resource_json_validation(service: SkillCreationService, tmp_path: Path) -> None:
    skill_dir = tmp_path / "json-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: json-skill\ndescription: demo\n---\n", encoding="utf-8")

    # Invalid JSON
    res_bad = await service.write_resource(
        skill_name="json-skill",
        resource_path="config.json",
        content="{\"key\": \"value\",}",  # trailing comma is invalid JSON
    )
    assert res_bad.success is False
    assert "JSON syntax error" in (res_bad.error or "")
    assert not (skill_dir / "config.json").exists()

    # Valid JSON
    res_ok = await service.write_resource(
        skill_name="json-skill",
        resource_path="config.json",
        content="{\"key\": \"value\"}",
    )
    assert res_ok.success is True
    assert (skill_dir / "config.json").exists()


@pytest.mark.asyncio
async def test_write_resource_yaml_validation(service: SkillCreationService, tmp_path: Path) -> None:
    skill_dir = tmp_path / "yaml-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: yaml-skill\ndescription: demo\n---\n", encoding="utf-8")

    # Invalid YAML (tabs/indentation error)
    res_bad = await service.write_resource(
        skill_name="yaml-skill",
        resource_path="schema.yaml",
        content="foo:\n  bar: 1\n bad_indent",
    )
    assert res_bad.success is False
    assert "YAML syntax error" in (res_bad.error or "")
    assert not (skill_dir / "schema.yaml").exists()

    # Valid YAML
    res_ok = await service.write_resource(
        skill_name="yaml-skill",
        resource_path="schema.yaml",
        content="foo:\n  bar: 1\n",
    )
    assert res_ok.success is True
    assert (skill_dir / "schema.yaml").exists()

    # Invalid .yml
    res_yml_bad = await service.write_resource(
        skill_name="yaml-skill",
        resource_path="config.yml",
        content="foo:\n  bar: [1, 2\n",
    )
    assert res_yml_bad.success is False
    assert "YAML syntax error" in (res_yml_bad.error or "")

    # Valid .yml
    res_yml_ok = await service.write_resource(
        skill_name="yaml-skill",
        resource_path="config.yml",
        content="enabled: true\n",
    )
    assert res_yml_ok.success is True
    assert (skill_dir / "config.yml").exists()


@pytest.mark.asyncio
async def test_write_resource_path_traversal_blocked(service: SkillCreationService, tmp_path: Path) -> None:
    skill_dir = tmp_path / "traversal-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: traversal-skill\ndescription: demo\n---\n", encoding="utf-8")

    res = await service.write_resource(
        skill_name="traversal-skill",
        resource_path="../../escaped.py",
        content="print('hacked')",
    )
    assert res.success is False
    assert "escapes skill directory" in (res.error or "")


@pytest.mark.asyncio
async def test_write_resource_nonexistent_skill(service: SkillCreationService) -> None:
    res = await service.write_resource(
        skill_name="non-existent-skill",
        resource_path="scripts/main.py",
        content="print('hello')",
    )
    assert res.success is False
    assert "not found" in (res.error or "")


@pytest.mark.asyncio
async def test_write_resource_empty_files(service: SkillCreationService, tmp_path: Path) -> None:
    skill_dir = tmp_path / "empty-files-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: empty-files-skill\ndescription: demo\n---\n", encoding="utf-8")

    # Empty python is valid AST
    res_py = await service.write_resource(
        skill_name="empty-files-skill",
        resource_path="empty.py",
        content="",
    )
    assert res_py.success is True

    # Empty JSON is invalid JSON
    res_json = await service.write_resource(
        skill_name="empty-files-skill",
        resource_path="empty.json",
        content="",
    )
    assert res_json.success is False
    assert "JSON syntax error" in (res_json.error or "")

    # Empty YAML safe_load is None (valid)
    res_yaml = await service.write_resource(
        skill_name="empty-files-skill",
        resource_path="empty.yaml",
        content="",
    )
    assert res_yaml.success is True

