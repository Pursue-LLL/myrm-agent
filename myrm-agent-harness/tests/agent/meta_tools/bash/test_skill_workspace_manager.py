"""SkillWorkspaceManager: a skill that is about to receive its saved settings runs from the files that shipped.

The agent can write anywhere in its workspace, the skill copy included, so a copy made once and reused would let an
edited script (or a module added beside it) run with the user's mailbox password. ``pristine=True`` replaces the copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.skill_workspace_manager import SkillWorkspaceManager
from myrm_agent_harness.toolkits.code_execution.workspace import Workspace, create_workspace_service

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs symlinks")

SKILL = "imap-smtp-email"
SHIPPED = "print('shipped')\n"


@pytest.fixture
def stored_skill(tmp_path: Path) -> str:
    skill = tmp_path / "storage" / SKILL
    (skill / "scripts" / "mail_client").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# mail\n")
    (skill / "scripts" / "email_manager.py").write_text(SHIPPED)
    (skill / "scripts" / "mail_client" / "transport.py").write_text("PORT = 993\n")
    return str(skill)


@pytest.fixture
async def workspace(tmp_path: Path) -> tuple[SkillWorkspaceManager, Workspace, Path]:
    service = create_workspace_service(root_dir=tmp_path / "root")
    workspace = await service.create("conversation")
    return SkillWorkspaceManager(service), workspace, Path(service.get_workspace_absolute_path(workspace))


def _script(workspace_dir: Path) -> Path:
    return workspace_dir / ".claude" / "skills" / SKILL / "scripts" / "email_manager.py"


async def test_an_existing_copy_is_reused_as_it_is_without_pristine(
    workspace: tuple[SkillWorkspaceManager, Workspace, Path], stored_skill: str
) -> None:
    manager, ws, workspace_dir = workspace
    await manager.ensure_skills_in_workspace(ws, [stored_skill])
    _script(workspace_dir).write_text("print('edited')\n")

    await manager.ensure_skills_in_workspace(ws, [stored_skill])

    assert _script(workspace_dir).read_text() == "print('edited')\n"


async def test_pristine_restores_an_edited_script(
    workspace: tuple[SkillWorkspaceManager, Workspace, Path], stored_skill: str
) -> None:
    manager, ws, workspace_dir = workspace
    await manager.ensure_skills_in_workspace(ws, [stored_skill])
    _script(workspace_dir).write_text("import os; print(os.environ)\n")

    paths = await manager.ensure_skills_in_workspace(ws, [stored_skill], pristine=True)

    assert paths == [str(workspace_dir / ".claude" / "skills" / SKILL)]
    assert _script(workspace_dir).read_text() == SHIPPED


async def test_pristine_removes_a_file_added_beside_the_shipped_ones(
    workspace: tuple[SkillWorkspaceManager, Workspace, Path], stored_skill: str
) -> None:
    manager, ws, workspace_dir = workspace
    await manager.ensure_skills_in_workspace(ws, [stored_skill])
    planted = workspace_dir / ".claude" / "skills" / SKILL / "scripts" / "mail_client" / "evil.py"
    planted.write_text("print('shadow')\n")

    await manager.ensure_skills_in_workspace(ws, [stored_skill], pristine=True)

    assert not planted.exists()
    assert (planted.parent / "transport.py").read_text() == "PORT = 993\n"


async def test_pristine_replaces_a_link_standing_for_the_skill_directory(
    workspace: tuple[SkillWorkspaceManager, Workspace, Path], stored_skill: str, tmp_path: Path
) -> None:
    manager, ws, workspace_dir = workspace
    outside = tmp_path / "outside"
    (outside / "scripts").mkdir(parents=True)
    (outside / "scripts" / "email_manager.py").write_text("print('outside')\n")
    skills_root = workspace_dir / ".claude" / "skills"
    skills_root.mkdir(parents=True)
    (skills_root / SKILL).symlink_to(outside, target_is_directory=True)

    await manager.ensure_skills_in_workspace(ws, [stored_skill], pristine=True)

    assert not (skills_root / SKILL).is_symlink()
    assert _script(workspace_dir).read_text() == SHIPPED
    assert (outside / "scripts" / "email_manager.py").read_text() == "print('outside')\n"


async def test_pristine_replaces_a_file_standing_for_the_skill_directory(
    workspace: tuple[SkillWorkspaceManager, Workspace, Path], stored_skill: str
) -> None:
    manager, ws, workspace_dir = workspace
    skills_root = workspace_dir / ".claude" / "skills"
    skills_root.mkdir(parents=True)
    (skills_root / SKILL).write_text("not a directory")

    await manager.ensure_skills_in_workspace(ws, [stored_skill], pristine=True)

    assert _script(workspace_dir).read_text() == SHIPPED


async def test_pristine_refuses_a_skills_root_that_is_a_link_and_leaves_its_target_alone(
    workspace: tuple[SkillWorkspaceManager, Workspace, Path], stored_skill: str, tmp_path: Path
) -> None:
    manager, ws, workspace_dir = workspace
    outside = tmp_path / "outside-skills"
    (outside / SKILL).mkdir(parents=True)
    keep = outside / SKILL / "keep.txt"
    keep.write_text("mine")
    (workspace_dir / ".claude").mkdir()
    (workspace_dir / ".claude" / "skills").symlink_to(outside, target_is_directory=True)

    paths = await manager.ensure_skills_in_workspace(ws, [stored_skill], pristine=True)

    assert paths == []
    assert keep.read_text() == "mine"
    assert not (outside / SKILL / "scripts").exists()
