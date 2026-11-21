"""Tests for the environment and git configuration the resilience header sets for a command."""

from __future__ import annotations

import os
import shlex
import shutil

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from myrm_agent_harness.toolkits.code_execution.session.models import SessionExecutionResult
from tests.toolkits.code_execution._session_helpers import make_config

# The product puts this script in front of every command, so a command here sources it first.
_SOURCE_HEADER = "source " + shlex.quote(
    os.path.join(
        os.path.dirname(__file__),
        "../../../src/myrm_agent_harness/agent/meta_tools/bash/scripts/resilience_init.sh",
    )
)


async def _execute_in_new_session(command: str) -> SessionExecutionResult:
    session = LocalPersistentSession(make_config())
    await session.start()
    try:
        return await session.execute(command)
    finally:
        await session.close()


class TestSmartEnvInjection:
    @pytest.mark.asyncio
    async def test_global_defense_env_vars(self) -> None:
        """Test that global defense environment variables (CI, NEXT_TELEMETRY_DISABLED) are set."""
        result = await _execute_in_new_session(
            f"unset CI\n{_SOURCE_HEADER}\nenv | grep -E '^(CI|NEXT_TELEMETRY_DISABLED)='"
        )
        assert "CI=1" in result.stdout
        assert "NEXT_TELEMETRY_DISABLED=1" in result.stdout

    @pytest.mark.asyncio
    async def test_a_ci_value_the_caller_set_stays(self) -> None:
        """A background job starts with ``CI=true``; the header does not turn that into ``1``."""
        result = await _execute_in_new_session(f"export CI=true\n{_SOURCE_HEADER}\necho ci=$CI")
        assert "ci=true" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        shutil.which("npm") is None,
        reason="npm is not installed in the current environment",
    )
    async def test_smart_local_env_injection_for_build(self) -> None:
        """Test that SKIP_ENV_VALIDATION is injected for build commands but not for normal commands."""
        config = make_config()
        session = LocalPersistentSession(config)
        await session.start()
        try:

            async def run_with_script(command: str) -> SessionExecutionResult:
                return await session.execute(f"{_SOURCE_HEADER}\n{command}")

            # Create a real package.json to test actual npm behavior
            await session.execute(
                'echo \'{"scripts": {"build": "env | grep -E \\"SKIP_ENV_VALIDATION|IGNORE_ENV_VALIDATION\\" || true", "test": "env | grep -E \\"SKIP_ENV_VALIDATION|IGNORE_ENV_VALIDATION\\" || true", "dev": "env | grep -E \\"SKIP_ENV_VALIDATION|IGNORE_ENV_VALIDATION\\" || true"}}\' > package.json'
            )

            # 1. Test npm run build (should inject)
            result = await run_with_script("npm run build")
            assert "SKIP_ENV_VALIDATION=1" in result.stdout
            assert "IGNORE_ENV_VALIDATION=1" in result.stdout

            # 2. Test npm test (should NOT inject)
            result2 = await run_with_script("npm test")
            assert "SKIP_ENV_VALIDATION=1" not in result2.stdout
            assert "IGNORE_ENV_VALIDATION=1" not in result2.stdout

            # 3. Test npm run dev (should inject)
            result3 = await run_with_script("npm run dev")
            assert "SKIP_ENV_VALIDATION=1" in result3.stdout

        finally:
            await session.execute("rm -f package.json")
            await session.close()


class TestGithubCredentialHelperEntry:
    """The header runs in front of every command, and git's environment configuration gets one helper entry."""

    @pytest.mark.asyncio
    async def test_running_the_header_again_in_one_shell_adds_no_second_entry(self) -> None:
        result = await _execute_in_new_session(
            f"unset GIT_CONFIG_COUNT\n{_SOURCE_HEADER}\n{_SOURCE_HEADER}\necho count=$GIT_CONFIG_COUNT"
        )
        assert "count=1" in result.stdout

    @pytest.mark.asyncio
    async def test_an_entry_the_shell_already_has_stays(self) -> None:
        result = await _execute_in_new_session(
            "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=cat\n"
            f"{_SOURCE_HEADER}\necho count=$GIT_CONFIG_COUNT\ngit config core.pager"
        )
        assert "count=2" in result.stdout
        assert "cat" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shell", ["bash", "/bin/bash"])
    async def test_the_header_loads_twice_in_strict_mode(self, shell: str) -> None:
        """``/bin/bash`` is the 3.2 that macOS ships, where an unset variable or empty array under ``set -u`` fails."""
        if shutil.which(shell) is None:
            pytest.skip(f"{shell} is not installed")
        script = f"set -euo pipefail; unset GIT_CONFIG_COUNT; {_SOURCE_HEADER}; {_SOURCE_HEADER}; echo strict-ok"
        result = await _execute_in_new_session(f"{shell} -c {shlex.quote(script)}")
        assert "strict-ok" in result.stdout
