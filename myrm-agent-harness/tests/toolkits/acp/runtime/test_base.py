"""Tests for the runtime base: child environment, response truncation, turn lifecycle, timeout and streaming truncation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from myrm_agent_harness.toolkits.acp.runtime._base import BaseRuntime, build_safe_env, truncate_response
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    BackendType,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)


class TestBuildSafeEnv:
    def test_strips_sensitive_keys(self) -> None:
        base = {
            "HOME": "/home/user",
            "OPENAI_API_KEY": "sk-secret",
            "ANTHROPIC_API_KEY": "ant-secret",
            "PATH": "/usr/bin",
        }
        cfg = RuntimeConfig(backend_type="acp", command="test")
        env = build_safe_env(cfg, base)
        assert "OPENAI_API_KEY" not in env
        assert "ANTHROPIC_API_KEY" not in env
        assert env["HOME"] == "/home/user"
        assert env["PATH"] == "/usr/bin"

    def test_inherits_only_the_core_variables(self) -> None:
        # A delegated CLI hands its environment on to every command the model runs, so what the operator
        # exported for other purposes (tokens, connection strings, agent sockets) never reaches it.
        base = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LANG": "en_US.UTF-8",
            "HTTPS_PROXY": "http://proxy:3128",
            "GITHUB_TOKEN": "ghp_secret",
            "AWS_ACCESS_KEY_ID": "AKIA",
            "DATABASE_URL": "postgres://user:pw@db/app",
            "SSH_AUTH_SOCK": "/tmp/agent.sock",
            "STRIPE_LIVE": "sk_live",
            "JAVA_HOME": "/opt/java",
        }
        cfg = RuntimeConfig(backend_type="acp", command="test")
        env = build_safe_env(cfg, base)
        assert env == {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LANG": "en_US.UTF-8",
            "HTTPS_PROXY": "http://proxy:3128",
        }

    def test_keeps_the_login_home_of_its_own_cli_only(self) -> None:
        base = {"CLAUDE_CONFIG_DIR": "/vol/claude", "CODEX_HOME": "/vol/codex", "PATH": "/usr/bin"}
        for command, kept, dropped in (
            ("claude", "CLAUDE_CONFIG_DIR", "CODEX_HOME"),
            ("/usr/local/bin/codex", "CODEX_HOME", "CLAUDE_CONFIG_DIR"),
        ):
            env = build_safe_env(RuntimeConfig(backend_type="cli", command=command), base)
            assert kept in env
            assert dropped not in env
        unknown = build_safe_env(RuntimeConfig(backend_type="cli", command="/opt/custom/agent"), base)
        assert "CLAUDE_CONFIG_DIR" not in unknown
        assert "CODEX_HOME" not in unknown

    def test_config_env_adds_what_a_backend_needs_beyond_the_core(self) -> None:
        cfg = RuntimeConfig(backend_type="cli", command="claude", env={"JAVA_HOME": "/opt/java"})
        env = build_safe_env(cfg, {"PATH": "/usr/bin", "JAVA_HOME": "/host/java"})
        assert env == {"PATH": "/usr/bin", "JAVA_HOME": "/opt/java"}

    def test_an_empty_base_is_an_empty_environment(self) -> None:
        env = build_safe_env(RuntimeConfig(backend_type="cli", command="claude"), {})
        assert env == {}

    def test_applies_config_env_after_strip(self) -> None:
        # api_key mode lets the host inject the provider key this backend bills against;
        # it is re-applied after the baseline strip removes the inherited one.
        base = {"OPENAI_API_KEY": "old-key"}
        cfg = RuntimeConfig(
            backend_type="acp",
            command="test",
            auth_mode="api_key",
            env={"OPENAI_API_KEY": "new-key"},
        )
        env = build_safe_env(cfg, base)
        assert env["OPENAI_API_KEY"] == "new-key"

    def test_subscription_drops_injected_secret(self) -> None:
        # subscription mode (default) forces the CLI onto its login session by dropping
        # any injected provider secret, so a stale key can't silently bill the user.
        base = {"OPENAI_API_KEY": "old-key"}
        cfg = RuntimeConfig(backend_type="acp", command="test", env={"OPENAI_API_KEY": "new-key"})
        env = build_safe_env(cfg, base)
        assert "OPENAI_API_KEY" not in env

    def test_a_node_cli_is_told_to_trust_the_system_store_while_enterprise_network_is_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        env = build_safe_env(RuntimeConfig(backend_type="cli", command="gemini"), {"PATH": "/usr/bin"})
        assert env == {"PATH": "/usr/bin", "NODE_USE_SYSTEM_CA": "1"}

    def test_the_backends_own_value_for_it_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        cfg = RuntimeConfig(backend_type="acp", command="gemini", env={"NODE_USE_SYSTEM_CA": "0"})
        assert build_safe_env(cfg, {"PATH": "/usr/bin"})["NODE_USE_SYSTEM_CA"] == "0"

    def test_nothing_is_added_while_strict_verification_is_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_TLS_STRICT", raising=False)
        env = build_safe_env(RuntimeConfig(backend_type="cli", command="gemini"), {"PATH": "/usr/bin"})
        assert "NODE_USE_SYSTEM_CA" not in env


class TestTruncateResponse:
    def test_no_truncation(self) -> None:
        assert truncate_response("short", 100) == "short"

    def test_truncation(self) -> None:
        result = truncate_response("a" * 200, 100)
        assert len(result) > 100
        assert "[truncated" in result


class TestBaseRuntime:
    @pytest.mark.asyncio
    async def test_get_info(self) -> None:
        rt = BaseRuntime("test-rt", RuntimeConfig(backend_type="acp", command="test"), "acp")
        info = await rt.get_info()
        assert info.name == "test-rt"
        assert info.backend_type == "acp"
        assert info.status == "stopped"

    @pytest.mark.asyncio
    async def test_close_sets_alive_false(self) -> None:
        rt = BaseRuntime("test-rt", RuntimeConfig(backend_type="acp", command="test"), "acp")
        rt._alive = True
        await rt.close()
        assert rt.is_alive is False

    @pytest.mark.asyncio
    async def test_cancel_suppresses_errors(self) -> None:
        rt = BaseRuntime("test-rt", RuntimeConfig(backend_type="acp", command="test"), "acp")
        await rt.cancel("s1")

    @pytest.mark.asyncio
    async def test_resume_returns_false(self) -> None:
        rt = BaseRuntime("test-rt", RuntimeConfig(backend_type="acp", command="test"), "acp")
        assert await rt.resume("s1") is False

    def test_capabilities_default(self) -> None:
        rt = BaseRuntime("test-rt", RuntimeConfig(backend_type="acp", command="test"), "acp")
        caps = rt.capabilities
        assert caps.supports_resume is False
        assert caps.supports_streaming is True


class _ScriptedRuntime(BaseRuntime):
    """A runtime whose turn is the ``turn`` a test gives it; it records the sessions it was asked to cancel."""

    def __init__(self, name: str, config: RuntimeConfig, backend_type: BackendType) -> None:
        super().__init__(name, config, backend_type)
        self.cancel_calls: list[str] = []

    def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
        raise NotImplementedError

    async def _do_run_turn(
        self,
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
        images: list[str] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]:
        async for event in self.turn(session_id):
            yield event

    async def _do_cancel(self, session_id: str) -> None:
        self.cancel_calls.append(session_id)


def _error_of(events: list[RuntimeEvent]) -> AcpError:
    error = next(e for e in events if e.type == RuntimeEventType.ERROR).data["error"]
    assert isinstance(error, AcpError)
    return error


class TestBaseRuntimeTimeout:
    """Tests for BaseRuntime timeout control in run_turn."""

    @pytest.mark.asyncio
    async def test_timeout_yields_error_event(self) -> None:
        class _SlowRuntime(_ScriptedRuntime):
            async def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="start")
                await asyncio.sleep(100)
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="never")

        rt = _SlowRuntime(
            "slow-rt",
            RuntimeConfig(backend_type="cli", command="x", timeout_seconds=1),
            "cli",
        )
        events: list[RuntimeEvent] = []
        async for e in rt.run_turn("hello", "s1"):
            events.append(e)

        types = [e.type for e in events]
        assert RuntimeEventType.TEXT_DELTA in types
        assert RuntimeEventType.ERROR in types
        error = _error_of(events)
        assert error.code == AcpErrorCode.TIMEOUT
        assert error.retryable is True

    @pytest.mark.asyncio
    async def test_runtime_exception_yields_error_event(self) -> None:
        class _BrokenRuntime(_ScriptedRuntime):
            async def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="before")
                raise RuntimeError("kaboom")

        rt = _BrokenRuntime("broken", RuntimeConfig(backend_type="cli", command="x"), "cli")
        events: list[RuntimeEvent] = []
        async for e in rt.run_turn("hello", "s1"):
            events.append(e)

        types = [e.type for e in events]
        assert RuntimeEventType.TEXT_DELTA in types
        assert RuntimeEventType.ERROR in types
        error = _error_of(events)
        assert error.code == AcpErrorCode.UNKNOWN
        assert "kaboom" in error.message

    @pytest.mark.asyncio
    async def test_timeout_cancels_process(self) -> None:
        class _SlowRuntime(_ScriptedRuntime):
            async def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="start")
                await asyncio.sleep(100)
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="never")

        rt = _SlowRuntime(
            "slow-rt",
            RuntimeConfig(backend_type="cli", command="x", timeout_seconds=1),
            "cli",
        )
        _ = [e async for e in rt.run_turn("hello", "s1")]

        assert rt.cancel_calls == ["s1"], "timeout must terminate the spawned process"

    @pytest.mark.asyncio
    async def test_runtime_exception_cancels_process(self) -> None:
        class _BrokenRuntime(_ScriptedRuntime):
            async def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="before")
                raise RuntimeError("kaboom")

        rt = _BrokenRuntime("broken", RuntimeConfig(backend_type="cli", command="x"), "cli")
        _ = [e async for e in rt.run_turn("hello", "s1")]

        assert rt.cancel_calls == ["s1"], "unexpected failure must clean up the spawned process"


class TestBaseRuntimeStreamTruncation:
    """Tests for BaseRuntime.run_turn streaming truncation (lines 134-151)."""

    @pytest.mark.asyncio
    async def test_truncation_stops_text_but_passes_non_text(self) -> None:
        class _VerboseRuntime(_ScriptedRuntime):
            async def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="x" * 30_000)
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="x" * 30_000)
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="should be dropped")
                yield create_event(RuntimeEventType.TOOL_START, session_id, tool_name="bash")
                yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

        cfg = RuntimeConfig(backend_type="cli", command="x", max_response_chars=50_000)
        rt = _VerboseRuntime("trunc-rt", cfg, "cli")
        events: list[RuntimeEvent] = []
        async for e in rt.run_turn("hello", "s1"):
            events.append(e)

        types = [e.type for e in events]
        text_events = [e for e in events if e.type == RuntimeEventType.TEXT_DELTA]
        assert any("[truncated" in str(e.data.get("content", "")) for e in text_events)
        assert RuntimeEventType.TOOL_START in types
        assert RuntimeEventType.DONE in types
        normal_text = [e for e in text_events if "[truncated" not in str(e.data.get("content", ""))]
        assert len(normal_text) == 1

    @pytest.mark.asyncio
    async def test_cancelled_error_propagated(self) -> None:
        class _CancelledRuntime(_ScriptedRuntime):
            async def turn(self, session_id: str) -> AsyncGenerator[RuntimeEvent]:
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="start")
                raise asyncio.CancelledError

        rt = _CancelledRuntime("cancel-rt", RuntimeConfig(backend_type="cli", command="x"), "cli")
        with pytest.raises(asyncio.CancelledError):
            async for _ in rt.run_turn("hello", "s1"):
                pass

    @pytest.mark.asyncio
    async def test_close_error_suppressed(self) -> None:
        class _FailClose(BaseRuntime):
            async def _do_close(self) -> None:
                raise RuntimeError("close boom")

        rt = _FailClose("fail", RuntimeConfig(backend_type="cli", command="x"), "cli")
        rt._alive = True
        await rt.close()
        assert rt.is_alive is False

    @pytest.mark.asyncio
    async def test_cancel_error_suppressed(self) -> None:
        class _FailCancel(BaseRuntime):
            async def _do_cancel(self, session_id: str) -> None:
                raise RuntimeError("cancel boom")

        rt = _FailCancel("fail", RuntimeConfig(backend_type="cli", command="x"), "cli")
        await rt.cancel("s1")
