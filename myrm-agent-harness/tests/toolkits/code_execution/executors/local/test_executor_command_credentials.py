"""Credentials and per-command env reach the shell of the command they belong to, and only that one.

The bash shell of a conversation is created once and reused for every later command. A credential is a property of
a command (which skill runs it, which approval granted it), not of the shell, so these tests run real commands in
one reused shell and assert what each of them can read.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.core.context_vars import approval_session_var
from myrm_agent_harness.core.security.ephemeral_credentials import command_digest, get_ephemeral_credential_store
from myrm_agent_harness.core.security.types import EphemeralUserCredential, user_credentials_ctx
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")

_GITHUB = EphemeralUserCredential(issuer="github", token="github-secret-1")
_FEISHU = EphemeralUserCredential(issuer="feishu", token="feishu-secret-1")


@contextlib.contextmanager
def _credentials(*credentials: EphemeralUserCredential) -> Iterator[None]:
    token = user_credentials_ctx.set(credentials)
    try:
        yield
    finally:
        user_credentials_ctx.reset(token)


def _hex(value: str) -> str:
    """How ``_read_command`` shows a value: a delivered credential is masked in anything a command prints, so the
    tests read it back as hex, which is not a form the output masking recognises."""
    return value.encode().hex()


def _read_command(name: str) -> str:
    return f"printenv {name} | tr -d '\\n' | od -An -tx1 | tr -d ' \\n' | grep . || echo NONE"


@pytest.fixture
async def executor(tmp_path: Path) -> AsyncIterator[LocalExecutor]:
    local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
    try:
        yield local
    finally:
        await local.close()


async def _run(
    executor: LocalExecutor,
    tmp_path: Path,
    command: str,
    *,
    issuers: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    result = await executor.execute_bash(
        ExecutionContext(
            code=command,
            session_id="one-conversation",
            work_dir=str(tmp_path),
            workspace_root=str(tmp_path),
            allowed_credential_issuers=issuers,
            env=env,
            timeout=30,
        )
    )
    assert result.success, result.error
    return result.stdout.strip()


class TestUserCredentials:
    async def test_credential_granted_after_the_shell_started_reaches_it(
        self, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        with _credentials():
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == "NONE"
        with _credentials(_GITHUB):
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == _hex("github-secret-1")

    async def test_refreshed_credential_replaces_the_old_one(self, executor: LocalExecutor, tmp_path: Path) -> None:
        with _credentials(_GITHUB):
            await _run(executor, tmp_path, _read_command("GITHUB_TOKEN"))
        with _credentials(EphemeralUserCredential(issuer="github", token="github-secret-2")):
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == _hex("github-secret-2")

    async def test_credential_does_not_outlive_its_command(self, executor: LocalExecutor, tmp_path: Path) -> None:
        with _credentials(_GITHUB):
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == _hex("github-secret-1")
        with _credentials():
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == "NONE"

    async def test_skill_command_after_a_generic_one_sees_only_its_declared_issuer(
        self, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        with _credentials(_GITHUB, _FEISHU):
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == _hex("github-secret-1")
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN"), issuers=[]) == "NONE"
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN"), issuers=["feishu"]) == "NONE"
            assert await _run(
                executor, tmp_path, _read_command("FEISHU_USER_ACCESS_TOKEN"), issuers=["feishu"]
            ) == _hex("feishu-secret-1")

    async def test_issuer_declared_by_a_later_command_reaches_the_running_shell(
        self, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        with _credentials(_GITHUB, _FEISHU):
            assert (
                await _run(executor, tmp_path, _read_command("FEISHU_USER_ACCESS_TOKEN"), issuers=["feishu"]) != "NONE"
            )
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN"), issuers=["github"]) == _hex(
                "github-secret-1"
            )
            assert await _run(executor, tmp_path, _read_command("FEISHU_USER_ACCESS_TOKEN"), issuers=[]) == "NONE"

    async def test_stream_path_delivers_credentials_to_a_running_shell(
        self, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        await _run(executor, tmp_path, "echo started")
        with _credentials(_GITHUB):
            chunks = [
                chunk
                async for chunk in executor.execute_bash_stream(
                    ExecutionContext(
                        code=_read_command("GITHUB_TOKEN"),
                        session_id="one-conversation",
                        work_dir=str(tmp_path),
                        workspace_root=str(tmp_path),
                        timeout=30,
                    )
                )
            ]
        assert _hex("github-secret-1") in "".join(chunks)
        with _credentials():
            assert await _run(executor, tmp_path, _read_command("GITHUB_TOKEN")) == "NONE"


class TestEphemeralCredentials:
    @pytest.fixture
    def approval_session(self) -> Iterator[str]:
        session_id = "approval-command-credentials"
        token = approval_session_var.set(session_id)
        try:
            yield session_id
        finally:
            approval_session_var.reset(token)
            get_ephemeral_credential_store().purge_session(session_id)

    async def test_one_time_credential_staged_for_a_running_shell_is_delivered_once(
        self, executor: LocalExecutor, tmp_path: Path, approval_session: str
    ) -> None:
        command = _read_command("DB_PASSWORD")
        await _run(executor, tmp_path, "echo started")
        store = get_ephemeral_credential_store()
        store.store_credential(
            approval_session,
            "DB_PASSWORD",
            "one-time-pw",
            expected_action_digest=command_digest(command),
        )

        assert await _run(executor, tmp_path, command) == _hex("one-time-pw")
        assert store.list_summaries(approval_session) == []
        assert await _run(executor, tmp_path, command) == "NONE"

    async def test_credential_follows_the_approved_command_through_script_preparation(
        self, executor: LocalExecutor, tmp_path: Path, approval_session: str
    ) -> None:
        """The agent issues one text, the bash tool prepares a longer script from it; the approval is about the first."""
        issued = _read_command("DB_PASSWORD")
        prepared = f"export CI=1\n\n{issued}"
        get_ephemeral_credential_store().store_credential(
            approval_session, "DB_PASSWORD", "one-time-pw", expected_action_digest=command_digest(issued)
        )

        result = await executor.execute_bash(
            ExecutionContext(
                code=prepared,
                original_code=issued,
                session_id="one-conversation",
                work_dir=str(tmp_path),
                workspace_root=str(tmp_path),
                timeout=30,
            )
        )

        assert result.success, result.error
        assert result.stdout.strip() == _hex("one-time-pw")

    async def test_credential_follows_the_approved_command_when_workspace_paths_are_rewritten(
        self, executor: LocalExecutor, tmp_path: Path, approval_session: str
    ) -> None:
        issued = "printenv DB_PASSWORD | tr -d '\\n' | od -An -tx1 | tr -d ' \\n' && echo && echo /workspace/data.csv"
        get_ephemeral_credential_store().store_credential(
            approval_session, "DB_PASSWORD", "one-time-pw", expected_action_digest=command_digest(issued)
        )

        output = await _run(executor, tmp_path, issued)

        credential_line, path_line = output.splitlines()
        assert credential_line == _hex("one-time-pw")
        assert path_line.endswith("/data.csv")
        assert not path_line.startswith("/workspace/")

    async def test_stream_path_follows_the_approved_command_through_script_preparation(
        self, executor: LocalExecutor, tmp_path: Path, approval_session: str
    ) -> None:
        issued = _read_command("DB_PASSWORD")
        get_ephemeral_credential_store().store_credential(
            approval_session, "DB_PASSWORD", "one-time-pw", expected_action_digest=command_digest(issued)
        )

        chunks = [
            chunk
            async for chunk in executor.execute_bash_stream(
                ExecutionContext(
                    code=f"export CI=1\n\n{issued}",
                    original_code=issued,
                    session_id="one-conversation",
                    work_dir=str(tmp_path),
                    workspace_root=str(tmp_path),
                    timeout=30,
                )
            )
        ]

        assert _hex("one-time-pw") in "".join(chunks)

    async def test_credential_is_not_delivered_to_a_command_that_was_not_approved(
        self, executor: LocalExecutor, tmp_path: Path, approval_session: str
    ) -> None:
        store = get_ephemeral_credential_store()
        store.store_credential(
            approval_session,
            "DB_PASSWORD",
            "one-time-pw",
            expected_action_digest=command_digest(_read_command("DB_PASSWORD")),
        )

        assert await _run(executor, tmp_path, f"{_read_command('DB_PASSWORD')} # edited") == "NONE"
        assert len(store.list_summaries(approval_session)) == 1


class TestPerCommandEnv:
    async def test_env_of_a_later_command_reaches_the_running_shell(
        self, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        await _run(executor, tmp_path, "echo started", env={"ORG": "first"})

        assert await _run(executor, tmp_path, _read_command("ORG"), env={"ORG": "second"}) == _hex("second")

    async def test_secret_named_env_is_still_stripped(self, executor: LocalExecutor, tmp_path: Path) -> None:
        await _run(executor, tmp_path, "echo started", env={"MY_API_TOKEN": "leak"})

        assert await _run(executor, tmp_path, _read_command("MY_API_TOKEN"), env={"MY_API_TOKEN": "leak"}) == "NONE"


class TestTracingCannotCarryCredentialsIntoOutput:
    """bash prints every line it runs under ``set -x`` / ``set -v``, and the exports of a command's credentials are lines."""

    @pytest.mark.parametrize("tracing", ["set -x", "set -v"])
    async def test_tracing_left_on_by_an_earlier_command_does_not_print_later_credentials(
        self, executor: LocalExecutor, tmp_path: Path, tracing: str
    ) -> None:
        await executor.execute_bash(
            ExecutionContext(
                code=tracing,
                session_id="one-conversation",
                work_dir=str(tmp_path),
                workspace_root=str(tmp_path),
                timeout=30,
            )
        )

        with _credentials(_GITHUB):
            output = await _run(executor, tmp_path, "echo hello", env={"ORG": "skill-secret-1"})

        assert output == "hello"
