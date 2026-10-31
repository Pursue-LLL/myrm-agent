"""The WhatsApp bridge's Node processes trust the operating system's certificates under the enterprise network setting.

Both processes the channel starts are Node: the npm install that fetches the bridge's dependencies and the bridge
itself. A Node process validates against its bundled roots, so behind a TLS-inspection proxy it rejects the chain the
host accepts unless it is told to read the system store. The desktop app strips ``NODE_EXTRA_CA_CERTS`` from its
children, which leaves this setting as the only way to tell them.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.channels.providers.whatsapp import bridge
from app.channels.providers.whatsapp.channel import WhatsAppChannel

_NODE_TRUST = "NODE_USE_SYSTEM_CA"


@dataclass(frozen=True)
class _Launch:
    """One process the bridge mixin started: its command line and the environment it was handed."""

    argv: tuple[str, ...]
    env: dict[str, str] | None


class _Process:
    pid = 4242
    returncode = 0
    stdin = None
    stdout = None
    stderr = None

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[_Launch]:
    """Record every process the bridge mixin starts instead of starting it; the bridge has no ``node_modules`` yet."""
    started: list[_Launch] = []

    async def record(*argv: str, **options: object) -> _Process:
        env = options.get("env")
        assert env is None or isinstance(env, dict)
        started.append(_Launch(argv, env))
        return _Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", record)
    monkeypatch.setattr(shutil, "which", lambda name: f"/opt/node/bin/{name}")
    monkeypatch.setattr(bridge, "_BRIDGE_DIR", tmp_path / "bridge")
    monkeypatch.delenv(_NODE_TRUST, raising=False)
    return started


@pytest.fixture
def channel(tmp_path: Path) -> WhatsAppChannel:
    return WhatsAppChannel(auth_dir=str(tmp_path / "auth"))


async def _spawned_env(launches: list[_Launch], channel: WhatsAppChannel, step: str) -> dict[str, str]:
    await getattr(channel, step)()
    assert len(launches) == 1
    env = launches[0].env
    assert env is not None
    return env


class TestEnterpriseNetworkSettingOn:
    @pytest.fixture(autouse=True)
    def _setting_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")

    async def test_the_npm_install_reads_the_system_store_and_keeps_the_rest_of_the_environment(
        self, launches: list[_Launch], channel: WhatsAppChannel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PATH", "/opt/node/bin")

        env = await _spawned_env(launches, channel, "_ensure_node_deps")

        assert launches[0].argv[1:] == ("install", "--production")
        assert env[_NODE_TRUST] == "1"
        assert env["PATH"] == "/opt/node/bin"

    async def test_the_bridge_reads_the_system_store_and_still_runs_without_a_proxy(
        self, launches: list[_Launch], channel: WhatsAppChannel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:8080")

        env = await _spawned_env(launches, channel, "_spawn_bridge")

        assert env[_NODE_TRUST] == "1"
        assert "HTTPS_PROXY" not in env

    async def test_a_value_the_operator_set_wins(
        self, launches: list[_Launch], channel: WhatsAppChannel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_NODE_TRUST, "0")

        assert (await _spawned_env(launches, channel, "_ensure_node_deps"))[_NODE_TRUST] == "0"


class TestEnterpriseNetworkSettingOff:
    @pytest.fixture(autouse=True)
    def _setting_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_TLS_STRICT", raising=False)

    @pytest.mark.parametrize("step", ["_ensure_node_deps", "_spawn_bridge"])
    async def test_neither_process_is_told_to_read_the_system_store(
        self, step: str, launches: list[_Launch], channel: WhatsAppChannel
    ) -> None:
        env = await _spawned_env(launches, channel, step)

        assert _NODE_TRUST not in env
