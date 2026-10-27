"""Local persistent session sandbox integration tests.

[INPUT]
- code_execution.sandbox (POS: Sandbox detection, policy and provider selection)
- code_execution.session.local_session (POS: Concrete local session with OS-level sandbox support)

[OUTPUT]
- Sandbox-enabled branch coverage: native provider, wrap_command fallback, provider cleanup, factory.

[POS]
Verifies the sandbox integration branches of ``LocalPersistentSession`` that the real
``auto`` detection skips on a plain developer machine (native provider path, wrap fallback,
provider cleanup, public factory).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.code_execution.sandbox import (
    SandboxStatus,
)
from myrm_agent_harness.toolkits.code_execution.sandbox.policy_bridge import UnsafeWorkspaceError
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxPolicy
from myrm_agent_harness.toolkits.code_execution.session.local_session import (
    LocalPersistentSession,
    create_persistent_session,
)
from myrm_agent_harness.toolkits.code_execution.session.models import SessionConfig


class _FakeSandboxProvider:
    """Minimal SandboxProvider stub recording call sites."""

    name = "fake-sandbox"

    def __init__(self) -> None:
        self.create_process = AsyncMock(return_value=None)
        self.wrap_calls: list[dict[str, object]] = []
        self.cleanup_called = False

    def wrap_command(self, **kwargs: object) -> tuple[str, tuple[str, ...]]:
        self.wrap_calls.append(kwargs)
        return str(kwargs["shell_path"]), tuple(kwargs["shell_args"])  # type: ignore[arg-type]

    def cleanup(self) -> None:
        self.cleanup_called = True


def _make_config() -> SessionConfig:
    return SessionConfig(
        session_id="sandbox-test",
        work_dir="/tmp",
        sandbox_mode="disable",
    )


def _enable_fake_provider(monkeypatch: pytest.MonkeyPatch, provider: _FakeSandboxProvider) -> None:
    status = SandboxStatus(True, provider.name, "enabled")
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        lambda mode, platform_info: (provider, status),
    )


def test_default_policy_follows_the_session_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The shell's sandbox policy is built from its config, not from a caller-assembled copy."""
    _enable_fake_provider(monkeypatch, _FakeSandboxProvider())

    writable = LocalPersistentSession(SessionConfig(session_id="w", work_dir=str(tmp_path), allow_network=False))
    readonly = LocalPersistentSession(SessionConfig(session_id="r", work_dir=str(tmp_path), readonly_workspace=True))

    assert writable._sandbox_policy is not None
    assert writable._sandbox_policy.writable_paths == (str(tmp_path),)
    assert writable._sandbox_policy.allow_network is False
    assert readonly._sandbox_policy is not None
    assert readonly._sandbox_policy.writable_paths == ()


def test_sandboxed_session_refuses_a_workspace_that_contains_a_dangerous_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_provider(monkeypatch, _FakeSandboxProvider())

    with pytest.raises(UnsafeWorkspaceError):
        LocalPersistentSession(SessionConfig(session_id="home", work_dir=os.path.expanduser("~")))


def test_unsandboxed_session_does_not_judge_the_workspace() -> None:
    """With no OS sandbox there is no grant to refuse; the policy is simply not built."""
    session = LocalPersistentSession(
        SessionConfig(session_id="off", work_dir=os.path.expanduser("~"), sandbox_mode="disable")
    )

    assert session._sandbox_policy is None


def test_explicit_policy_is_kept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _enable_fake_provider(monkeypatch, _FakeSandboxProvider())
    explicit = SandboxPolicy(writable_paths=(str(tmp_path / "x"),))

    session = LocalPersistentSession(SessionConfig(session_id="e", work_dir=str(tmp_path)), sandbox_policy=explicit)

    assert session._sandbox_policy is explicit


@pytest.mark.asyncio
async def test_create_process_uses_native_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandbox-enabled path returns the native process from the provider."""
    provider = _FakeSandboxProvider()
    fake_native = AsyncMock()
    provider.create_process = AsyncMock(return_value=fake_native)
    _enable_fake_provider(monkeypatch, provider)

    session = LocalPersistentSession(_make_config())
    try:
        proc = await session._create_process()
        assert proc is fake_native
        assert provider.create_process.called
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_create_process_falls_back_to_wrap_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider returning None falls back to wrap_command and spawns a real shell."""
    provider = _FakeSandboxProvider()
    _enable_fake_provider(monkeypatch, provider)

    session = LocalPersistentSession(_make_config())
    try:
        proc = await session._create_process()
        assert proc is not None
        assert provider.wrap_calls, "wrap_command must run when provider returns None"
        assert proc.pid is not None
        proc.kill()
        await proc.wait()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_close_cleans_up_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session close propagates cleanup to the sandbox provider."""
    provider = _FakeSandboxProvider()
    _enable_fake_provider(monkeypatch, provider)

    session = LocalPersistentSession(_make_config())
    await session.close()
    assert provider.cleanup_called


@pytest.mark.asyncio
async def test_create_process_sanitizes_credentials_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Child process launched via LocalPersistentSession must not inherit tokens/keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-secret")
    monkeypatch.setenv("NOISE_AUTH_TOKEN", "noise-token-val")
    monkeypatch.setenv("MYRM_VAULT_MASTER_KEY", "vault-master-pass")
    monkeypatch.setenv("SAFE_SYSTEM_VAR", "visible-val")

    provider = _FakeSandboxProvider()
    fake_native = AsyncMock()
    provider.create_process = AsyncMock(return_value=fake_native)
    _enable_fake_provider(monkeypatch, provider)

    session = LocalPersistentSession(_make_config())
    try:
        await session._create_process()
        # Verify passed env argument to sandbox provider
        call_kwargs = provider.create_process.call_args.kwargs
        passed_env = call_kwargs["env"]
        assert "OPENAI_API_KEY" not in passed_env
        assert "NOISE_AUTH_TOKEN" not in passed_env
        assert "MYRM_VAULT_MASTER_KEY" not in passed_env
        assert passed_env.get("SAFE_SYSTEM_VAR") == "visible-val"
    finally:
        await session.close()


def test_factory_returns_local_session() -> None:
    """create_persistent_session wires a LocalPersistentSession."""
    import asyncio

    session = create_persistent_session(_make_config())
    assert isinstance(session, LocalPersistentSession)
    assert session.config.sandbox_mode == "disable"
    asyncio.run(session.close())
