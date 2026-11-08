"""A skill's saved settings reach a bash command only when it is a plain call of that skill's restored script.

The settings carry the user's credentials (a mailbox password), the command is written by an agent that may be steered
by text it read (an inbound email), and the skill is recognised by a path inside the command. So the path alone must
not decide: a command that merely holds it gets nothing, and so does a call whose skill files could not be restored.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError
from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext, ExecutionResult

SETTINGS = {"EMAIL_IMAP_HOST": "imap.example.test", "EMAIL_IMAP_PASSWORD": "skill-pw-1"}
SKILL_DIR = ".claude/skills/imap-smtp-email"
PLAIN_CALL = f"python3 {SKILL_DIR}/scripts/email_manager.py check --limit 5"
STAGED = ["/ws/.claude/skills/imap-smtp-email"]


class _Run:
    """What one ``BashExecutor.execute`` handed to the code executor and to the skill workspace."""

    def __init__(self, executor: MagicMock, ensure: AsyncMock) -> None:
        self._executor = executor
        self._ensure = ensure

    @property
    def context(self) -> ExecutionContext:
        context: ExecutionContext = self._executor.execute_bash.call_args.args[0]
        return context

    @property
    def restored(self) -> bool:
        pristine: bool = self._ensure.call_args.kwargs.get("pristine", False)
        return pristine


@asynccontextmanager
async def _executor(
    *, staged: list[str] | None = None, result: ExecutionResult | None = None, settings: dict[str, str] | None = None
) -> AsyncIterator[tuple[BashExecutor, MagicMock, AsyncMock]]:
    code_executor = MagicMock()
    code_executor.config.network.allow_network = True
    code_executor.config.network.get_effective_allowed_hosts.return_value = []
    code_executor.config.local.max_execution_time = 120
    code_executor.get_executor_name.return_value = "mock"
    code_executor.execute_bash = AsyncMock(
        return_value=result or ExecutionResult(success=True, result=0, stdout="ok", stderr="", container_id="c")
    )
    bash = BashExecutor(code_executor, enable_skill_execution=False)
    bash.set_skill_env_map({"imap-smtp-email": SETTINGS if settings is None else settings})
    ensure = AsyncMock(return_value=STAGED if staged is None else staged)
    with (
        patch.object(bash._workspace_manager, "get_or_create", AsyncMock(return_value=(MagicMock(), None))),
        patch.object(bash._workspace_manager, "get_workspace_path", return_value="/ws"),
        patch.object(bash._workspace_manager, "update_workspace_timestamp", AsyncMock()),
        patch.object(bash._skill_manager, "ensure_skills_in_workspace", ensure),
        patch(
            "myrm_agent_harness.toolkits.code_execution.utils.WorkspacePathResolver.to_container_paths",
            return_value=["/workspace/.claude/skills/imap-smtp-email"],
        ),
        patch.object(bash, "_log_bash_command_execution", AsyncMock()),
    ):
        yield bash, code_executor, ensure


async def _execute(command: str, *, staged: list[str] | None = None, settings: dict[str, str] | None = None) -> _Run:
    async with _executor(staged=staged, settings=settings) as (bash, code_executor, ensure):
        await bash.execute(command, session_id="s", skill_paths=["/host/skills/imap-smtp-email"])
        return _Run(code_executor, ensure)


class TestPlainSkillCall:
    async def test_receives_the_settings_from_restored_files(self) -> None:
        run = await _execute(PLAIN_CALL)

        assert run.context.skill_env == SETTINGS
        assert run.context.env is not None
        assert run.context.env["EMAIL_IMAP_PASSWORD"] == "skill-pw-1"
        assert run.restored
        assert run.context.work_dir == "/workspace/.claude/skills/imap-smtp-email"
        assert run.context.enter_work_dir

    async def test_of_a_skill_without_settings_does_not_restore_anything(self) -> None:
        run = await _execute(PLAIN_CALL, settings={})

        assert run.context.skill_env is None
        assert not run.restored


class TestCommandThatOnlyHoldsTheSkillPath:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param(f"echo $EMAIL_IMAP_PASSWORD | base64 # {SKILL_DIR}/", id="path-in-a-comment"),
            pytest.param(f"echo $EMAIL_IMAP_PASSWORD {SKILL_DIR}/", id="path-as-an-operand"),
            pytest.param(f"{PLAIN_CALL} && env | base64", id="env-dump-after-the-call"),
            pytest.param(f"cat {SKILL_DIR}/SKILL.md", id="reading-a-skill-file"),
        ],
    )
    async def test_gets_no_settings_and_restores_nothing(self, command: str) -> None:
        run = await _execute(command)

        assert run.context.skill_env is None
        assert run.context.env is None or "EMAIL_IMAP_PASSWORD" not in run.context.env
        assert not run.restored


class TestSkillFilesThatCannotBeRestored:
    async def test_withhold_the_settings(self) -> None:
        run = await _execute(PLAIN_CALL, staged=[])

        assert run.restored
        assert run.context.skill_env is None
        assert run.context.env is None or "EMAIL_IMAP_PASSWORD" not in run.context.env


class TestWithheldSettingsAreExplainedToTheAgent:
    _FAILED = ExecutionResult(success=False, result=1, stdout="", stderr="missing host", error="failed")

    async def test_a_failed_command_that_was_not_given_the_settings_says_so(self) -> None:
        async with _executor(result=self._FAILED) as (bash, _, _):
            with pytest.raises(BashExecutionError) as failure:
                await bash.execute(f"{PLAIN_CALL} | head", session_id="s", skill_paths=["/host/skills/imap-smtp-email"])

        assert "saved settings of skill `imap-smtp-email` were not passed" in str(failure.value)
        assert f"`python3 {SKILL_DIR}/scripts/xxx.py ARGS`" in str(failure.value)

    async def test_a_failed_plain_call_does_not_claim_they_were_withheld(self) -> None:
        async with _executor(result=self._FAILED) as (bash, _, _):
            with pytest.raises(BashExecutionError) as failure:
                await bash.execute(PLAIN_CALL, session_id="s", skill_paths=["/host/skills/imap-smtp-email"])

        assert "were not passed" not in str(failure.value)
