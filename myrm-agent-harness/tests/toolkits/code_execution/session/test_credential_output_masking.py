"""A credential delivered to a command is hidden in everything that command prints.

Pattern-based scrubbing recognises credentials by their shape. A password typed for one command, or a token under any
variable name, passes it, so the credentials of a command (``CommandEnv.scoped``) are also masked by value: in the
returned output, in the live stream and in the tee file. These tests drive real shells.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.models import CommandEnv
from myrm_agent_harness.toolkits.code_execution.session.stream_buffer import ExecutionStreamBuffer
from myrm_agent_harness.toolkits.code_execution.session.value_masker import MASK, ValueMasker

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")

_SECRET = "correct-horse-battery-staple"
_ENV = CommandEnv(scoped={"DB_PASS": _SECRET})


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[LocalPersistentSession]:
    config = SessionConfig(session_id="credential-masking", work_dir=str(tmp_path), timeout=30, sandbox_mode="disable")
    shell = LocalPersistentSession(config)
    await shell.start()
    try:
        yield shell
    finally:
        await shell.close()


def _tee_logs(work_dir: Path) -> str:
    return "".join(log.read_text() for log in (work_dir / ".myrm" / "tee").glob("cmd_*.log"))


class TestResult:
    async def test_a_command_that_prints_its_credential_gets_it_masked(self, session: LocalPersistentSession) -> None:
        result = await session.execute('echo "password is $DB_PASS, ok"', env=_ENV)

        assert result.success
        assert result.stdout == f"password is {MASK}, ok"

    async def test_the_variable_name_does_not_matter(self, session: LocalPersistentSession) -> None:
        result = await session.execute("env | grep -c . >/dev/null && printenv DB_PASS", env=_ENV)

        assert result.stdout == MASK

    async def test_tracing_is_masked_too(self, session: LocalPersistentSession) -> None:
        result = await session.execute('set -x\necho "$DB_PASS" >/dev/null\nset +x', env=_ENV)

        assert result.stdout == f"+ echo {MASK}\n+ set +x"

    async def test_a_command_without_credentials_prints_what_it_prints(self, session: LocalPersistentSession) -> None:
        result = await session.execute(f"echo {_SECRET}")

        assert result.stdout == _SECRET

    async def test_only_the_command_it_was_delivered_to_is_masked(self, session: LocalPersistentSession) -> None:
        await session.execute("true", env=_ENV)

        assert (await session.execute(f"echo {_SECRET}")).stdout == _SECRET

    async def test_the_url_and_json_forms_of_a_credential_are_masked_too(self, session: LocalPersistentSession) -> None:
        env = CommandEnv(scoped={"DB_PASS": 'p@ss/w"rd1'})

        result = await session.execute(
            "printf 'url=%s json=%s raw=%s\\n' 'postgres://u:p%40ss%2Fw%22rd1@h' 'p@ss/w\\\"rd1' \"$DB_PASS\"", env=env
        )

        assert result.stdout == f"url=postgres://u:{MASK}@h json={MASK} raw={MASK}"

    @pytest.mark.parametrize("lead", [8180, 8188, 8190, 8191, 8192, 8193, 8200, 16380, 16384])
    async def test_a_value_that_straddles_a_read_is_masked(self, session: LocalPersistentSession, lead: int) -> None:
        result = await session.execute(f"head -c {lead} /dev/zero | tr '\\0' x && echo \"$DB_PASS tail\"", env=_ENV)

        assert result.stdout == f"{'x' * lead}{MASK} tail"


class TestStream:
    async def test_live_text_is_masked(self, session: LocalPersistentSession) -> None:
        chunks = [chunk async for chunk in session.execute_stream('echo "token=$DB_PASS"', env=_ENV)]

        assert "".join(chunks).strip() == f"token={MASK}"


class TestTeeFile:
    async def test_the_log_the_agent_can_read_back_holds_no_credential(
        self, session: LocalPersistentSession, tmp_path: Path
    ) -> None:
        await session.execute('echo "before $DB_PASS after"', env=_ENV)

        log = _tee_logs(tmp_path)
        assert f"before {MASK} after" in log
        assert _SECRET not in log


class TestStreamBuffer:
    """The buffer is the one place all three copies come from, so it is also tested without a shell, cut everywhere."""

    _EXIT = "__MYRM_EXIT_0123456789abcdef__"
    _END = "__MYRM_END_0123456789abcdef__"
    _OUTPUT = f"user={_SECRET}\nagain {_SECRET}\n"

    @pytest.mark.parametrize("cut", range(len(_OUTPUT.encode()) + len(_EXIT) + len(_END) + 3))
    def test_every_copy_is_masked_wherever_the_read_was_cut(self, cut: int) -> None:
        payload = f"{self._OUTPUT}{self._EXIT}0\n{self._END}\n".encode()
        buffer = ExecutionStreamBuffer(masker=ValueMasker([_SECRET]))

        live = buffer.process_bytes(payload[:cut], self._EXIT, self._END) + buffer.process_bytes(
            payload[cut:], self._EXIT, self._END
        )

        expected = f"user={MASK}\nagain {MASK}\n"
        assert buffer.done
        assert live == expected
        assert buffer.get_final_output() == expected

    def test_a_stream_that_ends_early_releases_what_it_held(self) -> None:
        fragment = _SECRET[:8]
        pending = "Z" * (len(self._EXIT) + 8)  # the buffer withholds this much of the tail until a marker is ruled out
        buffer = ExecutionStreamBuffer(masker=ValueMasker([_SECRET]))

        assert buffer.process_bytes(f"x {fragment}{pending}".encode(), self._EXIT, self._END) == "x "
        assert buffer.get_final_output() == f"x {fragment}{pending}"

    def test_without_a_masker_the_text_is_as_it_was(self) -> None:
        buffer = ExecutionStreamBuffer()

        buffer.process_bytes(f"{_SECRET}\n{self._EXIT}0\n{self._END}".encode(), self._EXIT, self._END)

        assert buffer.get_final_output() == f"{_SECRET}\n"
