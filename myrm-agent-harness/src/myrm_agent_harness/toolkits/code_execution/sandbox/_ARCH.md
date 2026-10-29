# sandbox/

## Overview
OS-level process sandbox for local/desktop execution. `SandboxPolicy.writable_paths` is the complete writable set besides the provider's scratch areas (such as `/tmp`): no provider grants the working directory implicitly, so an empty `writable_paths` yields a read-only workspace.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | OS-level process sandbox for local/desktop execution. | — |
| detector.py | Core | Auto-detect the best available sandbox provider. | ✅ |
| mount_security_gate.py | Core | Fail-closed dual-direction security gate for sandbox mounts (source & target traversal, UNC/SMB hash defense, container system root overwrite protection, symlink escape, device blocking, collision resolver, and refusal of a writable source that contains a dangerous root — a home directory or drive root — since write access to the tree is write access to `~/.ssh` and `/etc` inside it; read-only mounts are exempt). | ✅ |
| privacy_ladder.py | Core | Three-tier fail-closed privacy ladder for sandbox persistence and snapshot validation. | ✅ |
| policy_bridge.py | Core | Bridge between the permission engine's PathPolicy and OS-level SandboxPolicy. `build_workspace_sandbox_policy` is the one place a workspace root becomes the sandbox's writable tree, used by every local executor path (persistent shell, Python subprocess, background spawn): a root that equals or contains a dangerous root (a home directory, a drive root) raises `UnsafeWorkspaceError` (it is never dropped silently); a workspace inside one is granted for its own subtree; a read-only run grants nothing. The policy also carries `read_only_subpaths` from `protected_subpaths.py`. `granted_roots` become part of the policy through `sandbox_grant_roots` (each root passes the mount gate; a writable root joins the writable paths, a read-only one the readable paths, a read-only run makes all of them readable only; a writable root's git hooks and config stay read-only). | ✅ |
| protected_subpaths.py | Core | Finds, when a workspace policy is built, the git metadata (`EXECUTABLE_GIT_METADATA`: `.git/config`, `.git/hooks`) that stays read-only inside it: the workspace's own repository and its direct child directories, following a `.git` pointer file or link to a git directory inside the workspace (worktrees, submodules, `commondir`); the pointer entry itself is protected too. The submodules of every repository found are protected at any depth: their git directories below `modules/` and the `.git` pointer of the working tree each one names in `core.worktree`. Only existing paths are reported; every child directory is examined, so empty directories created by a sandboxed command cannot push a repository out of the scan. | ✅ |
| sandbox_types.py | Config | Foundation layer — all sandbox modules import from here. `movable_ancestors` names the directories above a read-only subpath that the process could rename, the one rule both providers use to pin them. | ✅ |

| Submodule | Description |
|-----------|-------------|
| providers/ | Built-in sandbox providers. |
