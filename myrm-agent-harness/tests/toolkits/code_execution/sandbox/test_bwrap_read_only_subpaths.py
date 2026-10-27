"""bwrap overlays a workspace's protected paths read-only on top of its writable bind.

[INPUT]
- code_execution.sandbox.providers.bwrap (POS: Linux bubblewrap (bwrap) sandbox provider)

[OUTPUT]
- Argument-vector checks (the provider only runs on Linux, so the vector is what is verified here).

[POS]
Guards the ordering a later mount relies on: the read-only overlay must come after the pins above it, and those
after the writable bind.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.sandbox.providers.bwrap import BwrapProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxPolicy


def _triples(args: tuple[str, ...]) -> list[tuple[str, str, str]]:
    return [(args[i], args[i + 1], args[i + 2]) for i in range(len(args) - 2) if args[i] in {"--bind", "--ro-bind"}]


def test_read_only_overlay_follows_the_writable_bind(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    config = workspace / ".git" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("[core]\n")
    policy = SandboxPolicy(writable_paths=(str(workspace),), read_only_subpaths=(str(config),))

    _, args = BwrapProvider().wrap_command("/bin/bash", (), str(workspace), policy)

    mounts = _triples(args)
    assert mounts.index(("--bind", str(workspace), str(workspace))) < mounts.index(
        ("--ro-bind", str(config), str(config))
    )


def test_directories_above_a_protected_path_become_mount_points_outer_first(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    config = workspace / "child" / ".git" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("[core]\n")
    policy = SandboxPolicy(writable_paths=(str(workspace),), read_only_subpaths=(str(config),))

    _, args = BwrapProvider().wrap_command("/bin/bash", (), str(workspace), policy)

    mounts = _triples(args)
    order = [
        ("--bind", str(workspace), str(workspace)),
        ("--bind", str(workspace / "child"), str(workspace / "child")),
        ("--bind", str(workspace / "child" / ".git"), str(workspace / "child" / ".git")),
        ("--ro-bind", str(config), str(config)),
    ]
    assert [mounts.index(mount) for mount in order] == sorted(mounts.index(mount) for mount in order)


def test_the_writable_root_and_a_symlinked_directory_are_not_pinned(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    real = workspace / "real"
    config = real / ".git" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("[core]\n")
    (workspace / "link").symlink_to(real)
    linked_config = workspace / "link" / ".git" / "config"
    policy = SandboxPolicy(writable_paths=(str(workspace),), read_only_subpaths=(str(linked_config),))

    _, args = BwrapProvider().wrap_command("/bin/bash", (), str(workspace), policy)

    binds = [mount for mount in _triples(args) if mount[0] == "--bind"]
    assert binds.count(("--bind", str(workspace), str(workspace))) == 1
    assert ("--bind", str(workspace / "link"), str(workspace / "link")) not in binds


def test_protected_path_that_does_not_exist_is_not_mounted(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    missing = workspace / ".git" / "hooks"
    policy = SandboxPolicy(writable_paths=(str(workspace),), read_only_subpaths=(str(missing),))

    _, args = BwrapProvider().wrap_command("/bin/bash", (), str(workspace), policy)

    assert str(missing) not in args
    assert str(missing.parent) not in args
