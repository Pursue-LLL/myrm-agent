"""The host workspace trust gate registry, and the cost of registering the agent layer's gate."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.mcp.trust_gate import (
    WorkspaceTrustGate,
    get_workspace_trust_gate,
    set_workspace_trust_gate,
)

_HARNESS_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _HARNESS_ROOT / "src"


class _AllowingGate:
    def get_trust_level(self) -> object:
        return "trusted"

    def assert_mcp_spawn_allowed(
        self,
        *,
        workspace_root: str | None,
        cwd: str | None,
        plugin_root: str | None,
        trust_level: object,
    ) -> None:
        return None


@pytest.fixture
def restored_gate() -> Iterator[None]:
    previous = get_workspace_trust_gate()
    yield
    set_workspace_trust_gate(previous)


def test_registered_gate_is_returned_until_it_is_cleared(restored_gate: None) -> None:
    gate: WorkspaceTrustGate = _AllowingGate()

    set_workspace_trust_gate(gate)
    assert get_workspace_trust_gate() is gate

    set_workspace_trust_gate(None)
    assert get_workspace_trust_gate() is None


def test_registering_the_agent_gate_does_not_load_the_mcp_sdk() -> None:
    """A run pays for the MCP SDK when it connects to a server, not when the trust package is imported."""
    script = textwrap.dedent(
        """
        import sys

        import myrm_agent_harness.agent.security.workspace_trust as trust
        from myrm_agent_harness.toolkits.mcp.trust_gate import get_workspace_trust_gate

        gate = get_workspace_trust_gate()
        assert gate is not None and type(gate).__module__ == trust.__name__, gate
        loaded = sorted(name for name in sys.modules if name == "mcp" or name.startswith("mcp."))
        assert not loaded, loaded[:5]
        """
    )
    env = os.environ.copy()
    inherited = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(_SRC_PATH) if not inherited else f"{_SRC_PATH}{os.pathsep}{inherited}"

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_HARNESS_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
