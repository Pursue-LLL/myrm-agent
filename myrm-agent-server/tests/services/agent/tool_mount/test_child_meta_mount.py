"""resolve_child_meta_mount offers a delegated child only the file/shell meta tools its capability can use."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.sub_agents.spawn_capability import (
    derive_readonly_capability,
    derive_spawn_capability,
    derive_verifier_capability,
)
from myrm_agent_harness.core.security.ocap import CapabilityHandle, capability_scope, sign_capability_handle

from app.services.agent.tool_mount import resolve_child_meta_mount


def _writer(workspace: Path) -> CapabilityHandle:
    parent = SimpleNamespace(_last_context={"workspace_path": str(workspace)})
    return derive_spawn_capability(parent_agent=parent, agent_type="writer", readonly=False)


def _expired(handle: CapabilityHandle) -> CapabilityHandle:
    unsigned = replace(handle, expires_at=handle.issued_at - 1.0, signature="")
    return replace(unsigned, signature=sign_capability_handle(unsigned))


def test_a_child_bound_to_no_handle_keeps_the_full_surface() -> None:
    mount = resolve_child_meta_mount()

    assert mount == {"file_access_mode": FileAccessMode.FULL, "enable_shell_tools": True}


def test_a_writer_keeps_the_full_surface(tmp_path: Path) -> None:
    with capability_scope(_writer(tmp_path)):
        mount = resolve_child_meta_mount()

    assert mount == {"file_access_mode": FileAccessMode.FULL, "enable_shell_tools": True}


def test_a_verifier_reads_and_runs_commands_but_is_not_offered_the_write_tools() -> None:
    with capability_scope(derive_verifier_capability("verifier")):
        mount = resolve_child_meta_mount()

    assert mount == {"file_access_mode": FileAccessMode.WORKSPACE_READ_ONLY, "enable_shell_tools": True}


def test_a_read_only_child_is_offered_neither_the_write_tools_nor_the_shell() -> None:
    with capability_scope(derive_readonly_capability("reviewer")):
        mount = resolve_child_meta_mount()

    assert mount == {"file_access_mode": FileAccessMode.WORKSPACE_READ_ONLY, "enable_shell_tools": False}


def test_an_expired_handle_is_offered_nothing_it_could_not_use(tmp_path: Path) -> None:
    """The mount asks the same question the executor asks, so an unusable handle withholds WRITE and EXECUTE."""
    with capability_scope(_expired(_writer(tmp_path))):
        mount = resolve_child_meta_mount()

    assert mount == {"file_access_mode": FileAccessMode.WORKSPACE_READ_ONLY, "enable_shell_tools": False}
