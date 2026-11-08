"""A skill's saved settings through the real chain: BashExecutor, skill workspace, LocalExecutor and a real shell.

Each test is one way an agent steered by untrusted text could try to read the settings of a skill it did not call: a
command that only holds the skill path, a script of the skill it edited first, a skill directory it moved away. The
skill script prints how long its password is, which the output masking does not hide. A skill command also has to run
in the skill's directory whatever the commands before it did.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.agent.meta_tools.bash._executor.skill_workspace_manager import SkillWorkspaceManager
from myrm_agent_harness.agent.meta_tools.bash._executor.workspace_manager import WorkspaceManager
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.workspace import create_workspace_service

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")

SKILL = "demo"
PLAIN_CALL = f"python3 .claude/skills/{SKILL}/scripts/who.py"
SETTINGS = {"EMAIL_IMAP_HOST": "imap.example.test", "EMAIL_IMAP_PASSWORD": "skill-pw-11"}
SCRIPT = (
    "import os\n"
    "print('dir=' + os.path.basename(os.getcwd()))\n"
    "print('host=' + os.environ.get('EMAIL_IMAP_HOST', '-'))\n"
    "print('pwlen=' + str(len(os.environ.get('EMAIL_IMAP_PASSWORD', ''))))\n"
)
PASSWORD_LENGTH = f"pwlen={len(SETTINGS['EMAIL_IMAP_PASSWORD'])}"


@dataclass(frozen=True)
class Agent:
    bash: BashExecutor
    stored_skill: str
    workspace_dir: Path

    @property
    def skill_dir(self) -> Path:
        """The workspace copy of the skill, which the agent can reach with its file tools."""
        return self.workspace_dir / ".claude" / "skills" / SKILL

    async def run(self, command: str) -> str:
        result = await self.bash.execute(command, session_id="conversation", skill_paths=[self.stored_skill])
        return str(result["stdout"]).strip()


@pytest.fixture
async def agent(tmp_path: Path) -> AsyncIterator[Agent]:
    stored = tmp_path / "storage" / SKILL
    (stored / "scripts").mkdir(parents=True)
    (stored / "SKILL.md").write_text("# demo\n")
    (stored / "scripts" / "who.py").write_text(SCRIPT)

    service = create_workspace_service(root_dir=tmp_path / "root")
    workspace = await service.create("conversation")
    workspace_dir = service.get_workspace_absolute_path(workspace)
    local = LocalExecutor(ExecutionConfig(), workspace_path=workspace_dir)
    bash = BashExecutor(local, enable_skill_execution=False)
    bash._workspace_manager = WorkspaceManager(service)
    bash._skill_manager = SkillWorkspaceManager(service)
    bash.set_skill_env_map({SKILL: SETTINGS})
    try:
        yield Agent(bash, str(stored), Path(workspace_dir))
    finally:
        await local.close()


async def test_a_plain_call_gets_the_settings_on_every_call(agent: Agent) -> None:
    for _ in range(2):
        printed = await agent.run(PLAIN_CALL)

        assert "host=imap.example.test" in printed
        assert PASSWORD_LENGTH in printed


async def test_a_command_that_only_holds_the_skill_path_gets_nothing(agent: Agent) -> None:
    assert await agent.run(f"echo $EMAIL_IMAP_PASSWORD | wc -c # .claude/skills/{SKILL}/") == "1"


async def test_a_script_the_agent_edited_is_restored_before_it_gets_the_settings(agent: Agent) -> None:
    await agent.run(PLAIN_CALL)
    (agent.skill_dir / "scripts" / "who.py").write_text("print('tampered')\n")

    printed = await agent.run(PLAIN_CALL)

    assert "tampered" not in printed
    assert PASSWORD_LENGTH in printed


async def test_a_skill_directory_the_agent_moved_away_does_not_run_in_its_place(agent: Agent) -> None:
    await agent.run(PLAIN_CALL)
    moved = agent.skill_dir.with_name("demo-moved")
    agent.skill_dir.rename(moved)
    (moved / "scripts" / "who.py").write_text("print('tampered')\n")

    printed = await agent.run(PLAIN_CALL)

    assert "tampered" not in printed
    assert PASSWORD_LENGTH in printed


@pytest.mark.parametrize("settings", [SETTINGS, {}], ids=["with-settings", "without-settings"])
async def test_a_skill_call_runs_in_the_skill_directory_after_other_commands(
    agent: Agent, settings: dict[str, str]
) -> None:
    agent.bash.set_skill_env_map({SKILL: settings})
    await agent.run("echo before")

    assert f"dir={SKILL}" in await agent.run(PLAIN_CALL)


async def test_the_shell_is_left_where_it_was_by_a_skill_call(agent: Agent) -> None:
    before = await agent.run("pwd")

    await agent.run(PLAIN_CALL)

    assert await agent.run("pwd") == before
