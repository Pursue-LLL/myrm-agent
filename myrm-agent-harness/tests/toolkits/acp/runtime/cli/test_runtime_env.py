"""The environment a CLI turn runs in: what the dialect adds and what the operator can still decide."""

from __future__ import annotations

import os
import sys

import pytest

from ._fakes import FakeCli, make_runtime, run_turn

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")


def _child_env(fake_cli: FakeCli, name: str = "claude") -> dict[str, str]:
    env = fake_cli.calls(name)[0]["env"]
    assert isinstance(env, dict)
    return env


class TestDialectDefaults:
    @pytest.mark.asyncio
    async def test_claude_is_told_not_to_wait_for_background_tasks(self, fake_cli: FakeCli) -> None:
        await run_turn(make_runtime(fake_cli))

        assert _child_env(fake_cli)["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"

    @pytest.mark.asyncio
    async def test_codex_gets_no_claude_setting(self, fake_cli: FakeCli) -> None:
        await run_turn(make_runtime(fake_cli, "codex"))

        assert "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" not in _child_env(fake_cli, "codex")

    @pytest.mark.asyncio
    async def test_the_configured_env_beats_a_dialect_default(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli, env={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "0"})

        await run_turn(runtime)

        assert _child_env(fake_cli)["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "0"


class TestHostEnvironment:
    """A CLI hands its environment on to every command the model runs, so it gets the core variables only."""

    @pytest.mark.asyncio
    async def test_the_operators_secrets_stay_behind_and_the_cli_keeps_its_own_login_home(
        self, fake_cli: FakeCli, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_canary")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-canary")
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@db/app")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/vol/claude")
        monkeypatch.setenv("CODEX_HOME", "/vol/codex")

        await run_turn(make_runtime(fake_cli))

        env = _child_env(fake_cli)
        assert not {"GITHUB_TOKEN", "OPENAI_API_KEY", "DATABASE_URL", "CODEX_HOME"} & env.keys()
        assert env["CLAUDE_CONFIG_DIR"] == "/vol/claude"
        assert env["PATH"] == os.environ["PATH"]

    @pytest.mark.asyncio
    async def test_an_api_key_the_host_injects_reaches_the_cli_in_api_key_mode_only(self, fake_cli: FakeCli) -> None:
        injected = {"ANTHROPIC_API_KEY": "sk-injected"}

        await run_turn(make_runtime(fake_cli, auth_mode="api_key", env=injected))
        await run_turn(make_runtime(fake_cli, auth_mode="subscription", env=injected))

        calls = fake_cli.calls()
        assert calls[0]["env"]["ANTHROPIC_API_KEY"] == "sk-injected"
        assert "ANTHROPIC_API_KEY" not in calls[1]["env"]
