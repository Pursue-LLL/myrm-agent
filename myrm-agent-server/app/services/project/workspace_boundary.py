"""Project workspace boundary enforcement.

[INPUT]
target_path: 目标文件或目录路径
workspace_root: 项目沙箱绑定的工作区根目录

[OUTPUT]
validate_project_workspace_boundary: 校验目标路径是否拘禁在项目工作区根目录下
assert_project_workspace_boundary: 断言并返回规范化路径，越界直接抛出 PermissionError
is_cross_project_workspace_collision: 校验两个项目工作区是否存在路径重叠碰撞

[POS]
项目沙箱零泄漏工作区物理边界哨兵。拦截跨项目文件越界、软链接穿透与路径遍历攻击。
"""

from __future__ import annotations

import os
from pathlib import Path


class ProjectWorkspaceEscapeError(PermissionError):
    """Raised when an operation attempts to escape the project workspace boundary."""


def validate_project_workspace_boundary(
    target_path: str | Path,
    workspace_root: str | Path,
) -> bool:
    """Validate that target_path strictly resolves within workspace_root.

    Resolves symlinks and relative segments (e.g. `..`) to eliminate
    path traversal escapes across project boundaries.
    """
    if not target_path or not workspace_root:
        return False

    real_root = os.path.realpath(os.path.abspath(str(workspace_root)))
    real_target = os.path.realpath(os.path.abspath(str(target_path)))

    if real_target == real_root:
        return True

    # Ensure target is a strict subdirectory of root
    root_prefix = real_root if real_root.endswith(os.sep) else real_root + os.sep
    return real_target.startswith(root_prefix)


def assert_project_workspace_boundary(
    target_path: str | Path,
    workspace_root: str | Path,
) -> str:
    """Assert target_path resides within workspace_root, returning the resolved path.

    Raises:
        ProjectWorkspaceEscapeError: If target_path resolves outside workspace_root.
    """
    real_root = os.path.realpath(os.path.abspath(str(workspace_root)))
    real_target = os.path.realpath(os.path.abspath(str(target_path)))

    if not validate_project_workspace_boundary(real_target, real_root):
        raise ProjectWorkspaceEscapeError(
            f"Access denied: target path '{target_path}' escapes project workspace boundary '{workspace_root}'"
        )
    return real_target


def is_cross_project_workspace_collision(
    workspace_a: str | Path,
    workspace_b: str | Path,
) -> bool:
    """Check if two project workspaces collide (identical or nested within each other)."""
    if not workspace_a or not workspace_b:
        return False

    real_a = os.path.realpath(os.path.abspath(str(workspace_a)))
    real_b = os.path.realpath(os.path.abspath(str(workspace_b)))

    if real_a == real_b:
        return True

    prefix_a = real_a if real_a.endswith(os.sep) else real_a + os.sep
    prefix_b = real_b if real_b.endswith(os.sep) else real_b + os.sep

    return real_b.startswith(prefix_a) or real_a.startswith(prefix_b)
