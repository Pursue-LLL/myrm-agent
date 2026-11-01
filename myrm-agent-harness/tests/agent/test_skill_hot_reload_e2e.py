"""End-to-end skill hot reload tests.

Skills are edited, added and deleted by editors, the skill creation service and the market while a session is
running. The backend reads the skills directory on every listing, so each of those changes must be visible in
the very next listing, with no watcher and no waiting.

[INPUT]
- backends.skills.local::LocalSkillBackend (POS: the directory-backed skill source under test)
- real files in a temp directory (POS: the file system decides what is a skill, nothing is faked)

[OUTPUT]
- test_backend_uses_updated_skill_immediately: an edit is seen by the next listing
- test_backend_detects_new_skill: a skill created after the first listing is seen by the next one
- test_backend_detects_deleted_skill: a skill deleted after the first listing is gone from the next one

[POS]
End-to-end tests for skill hot reload at the backend level.
"""

from pathlib import Path

import pytest

from myrm_agent_harness.backends.skills.local import LocalSkillBackend

_SKILL_TEMPLATE = """---
name: {name}
description: {description}
version: "{version}"
---

# {name}

{body}
"""


def _write_skill(root: Path, name: str, *, description: str, version: str = "1.0.0", body: str = "Body.") -> Path:
    skill_md = root / name / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        _SKILL_TEMPLATE.format(name=name, description=description, version=version, body=body), encoding="utf-8"
    )
    return skill_md


@pytest.mark.asyncio
async def test_backend_uses_updated_skill_immediately(tmp_path: Path) -> None:
    skill_md = _write_skill(tmp_path, "test-skill", description="Test skill version 1")
    backend = LocalSkillBackend(skills_dir=tmp_path)

    skills_v1 = await backend.list_skills()
    assert [(skill.name, skill.version) for skill in skills_v1] == [("test-skill", "1.0.0")]
    assert "Test skill version 1" in skills_v1[0].description

    _write_skill(tmp_path, "test-skill", description="Test skill version 2", version="2.0.0", body="Changed.")

    skills_v2 = await backend.list_skills()
    assert [(skill.name, skill.version) for skill in skills_v2] == [("test-skill", "2.0.0")], (
        f"Hot reload failed: the backend still lists the old version of {skill_md}"
    )
    assert "Test skill version 2" in skills_v2[0].description


@pytest.mark.asyncio
async def test_backend_detects_new_skill(tmp_path: Path) -> None:
    backend = LocalSkillBackend(skills_dir=tmp_path)
    assert await backend.list_skills() == []

    _write_skill(tmp_path, "new-skill", description="Newly created skill")

    skills_after = await backend.list_skills()
    assert [skill.name for skill in skills_after] == ["new-skill"]


@pytest.mark.asyncio
async def test_backend_detects_deleted_skill(tmp_path: Path) -> None:
    skill_md = _write_skill(tmp_path, "temp-skill", description="Temporary skill")
    backend = LocalSkillBackend(skills_dir=tmp_path)
    assert [skill.name for skill in await backend.list_skills()] == ["temp-skill"]

    skill_md.unlink()
    skill_md.parent.rmdir()

    assert await backend.list_skills() == []
