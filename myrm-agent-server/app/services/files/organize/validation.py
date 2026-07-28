"""Validate workspace organize plans.

[INPUT]
- app.services.files.organize.types::OrganizePlan (POS: organize 领域模型 SSOT)
- _resolve_workspace / _validate_target (local): workspace 解析 + 路径安全校验

[OUTPUT]
- validate_organize_plan: 返回 OrganizeValidationIssue 列表（空=通过）；含 duplicate_src / dst_collision 等

[POS]
Organize plan 六层路径安全校验：scope、depth、collision、protected paths、mtime TOCTOU。
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath

from app.services.files.organize.types import (
    OrganizePlan,
    OrganizePlanItem,
    OrganizeValidationIssue,
)

MAX_ORGANIZE_ITEMS = 500
MAX_ORGANIZE_DEPTH = 3
_ORGANIZE_PROTECTED_BASENAMES: frozenset[str] = frozenset(
    {".git", ".env", ".organize-plan.json"},
)
_ORGANIZE_PROTECTED_PREFIXES: tuple[str, ...] = (".env.",)


def _relative_depth(scope_root: str, dst: str) -> int:
    scope = PurePosixPath(scope_root.replace("\\", "/").strip("/"))
    target = PurePosixPath(dst.replace("\\", "/").strip("/"))
    if scope == PurePosixPath("."):
        return len(target.parts)
    try:
        rel = target.relative_to(scope)
    except ValueError:
        rel = target
    return len(rel.parts)


def _is_protected_basename(name: str) -> bool:
    if name in _ORGANIZE_PROTECTED_BASENAMES:
        return True
    return any(name.startswith(prefix) for prefix in _ORGANIZE_PROTECTED_PREFIXES)


def _resolve_workspace(workspace: str) -> str:
    """Resolve and validate workspace root (avoids api-layer import)."""
    from myrm_agent_harness.core.security.path_security import is_dangerous_path

    from app.core.utils.errors import validation_error

    resolved = os.path.realpath(os.path.expanduser(workspace))
    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied for workspace: {workspace}")
    if not os.path.isdir(resolved):
        raise validation_error(f"Workspace is not a directory: {workspace}")
    return resolved


def _validate_target(target: str, workspace: str, *, allow_sensitive: bool = False) -> str:
    """Resolve target path and run boundary + danger + sensitive checks."""
    from myrm_agent_harness.core.security.path_security import (
        is_dangerous_path,
        is_sensitive_file,
        is_within_boundary,
    )

    from app.core.utils.errors import validation_error

    resolved = os.path.realpath(os.path.expanduser(target))
    if not is_within_boundary(resolved, workspace):
        raise validation_error("Path is outside workspace boundary")
    if is_dangerous_path(resolved):
        raise validation_error("Access denied: dangerous path")
    if not allow_sensitive and is_sensitive_file(resolved):
        raise validation_error("Access denied: sensitive file")
    return resolved


def validate_organize_plan(workspace: str, plan: OrganizePlan) -> list[OrganizeValidationIssue]:
    """Return validation issues; empty list means plan is executable."""
    issues: list[OrganizeValidationIssue] = []
    ws = _resolve_workspace(workspace)

    scope_resolved = _validate_target(
        os.path.join(ws, plan.scope_root) if not os.path.isabs(plan.scope_root) else plan.scope_root,
        ws,
        allow_sensitive=True,
    )

    if not os.path.isdir(scope_resolved):
        issues.append(
            OrganizeValidationIssue(
                index=-1,
                code="scope_not_directory",
                message="Scope root is not a directory",
            )
        )
        return issues

    if len(plan.items) > MAX_ORGANIZE_ITEMS:
        issues.append(
            OrganizeValidationIssue(
                index=-1,
                code="too_many_items",
                message=f"Plan exceeds {MAX_ORGANIZE_ITEMS} items",
            )
        )
        return issues

    if not plan.items:
        issues.append(
            OrganizeValidationIssue(
                index=-1,
                code="empty_plan",
                message="Plan has no items",
            )
        )
        return issues

    seen_dst: set[str] = set()
    seen_src: set[str] = set()
    for index, item in enumerate(plan.items):
        issues.extend(
            _validate_item(ws, scope_resolved, plan.scope_root, index, item, seen_dst, seen_src)
        )

    return issues


def _validate_item(
    workspace: str,
    scope_resolved: str,
    scope_root: str,
    index: int,
    item: OrganizePlanItem,
    seen_dst: set[str],
    seen_src: set[str],
) -> list[OrganizeValidationIssue]:
    issues: list[OrganizeValidationIssue] = []

    src_basename = os.path.basename(item.src.rstrip("/"))
    dst_basename = os.path.basename(item.dst.rstrip("/"))
    if _is_protected_basename(src_basename) or _is_protected_basename(dst_basename):
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="protected_name",
                message=f"Protected basename in move: {item.src} -> {item.dst}",
            )
        )
        return issues

    try:
        src_resolved = _resolve_plan_path(workspace, item.src)
        dst_resolved = _resolve_plan_path(workspace, item.dst)
        _validate_target(src_resolved, workspace, allow_sensitive=True)
        _validate_target(os.path.dirname(dst_resolved), workspace, allow_sensitive=True)
    except Exception as exc:  # validation_error from workspace_ops
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="path_invalid",
                message=str(exc),
            )
        )
        return issues

    src_key = src_resolved.lower()
    if src_key in seen_src:
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="duplicate_src",
                message=f"Duplicate source: {item.src}",
            )
        )
    else:
        seen_src.add(src_key)

    if not os.path.exists(src_resolved):
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="src_missing",
                message=f"Source does not exist: {item.src}",
            )
        )
        return issues

    if not _path_within_scope(src_resolved, scope_resolved):
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="src_outside_scope",
                message=f"Source outside scope: {item.src}",
            )
        )

    rel_dst = _relative_to_workspace(workspace, item.dst)
    depth = _relative_depth(scope_root, rel_dst)
    if depth > MAX_ORGANIZE_DEPTH:
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="depth_exceeded",
                message=f"Destination depth {depth} exceeds max {MAX_ORGANIZE_DEPTH}",
            )
        )

    dst_key = dst_resolved.lower()
    if dst_key in seen_dst:
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="dst_collision",
                message=f"Duplicate destination: {item.dst}",
            )
        )
    else:
        seen_dst.add(dst_key)

    if os.path.exists(dst_resolved):
        issues.append(
            OrganizeValidationIssue(
                index=index,
                code="dst_exists",
                message=f"Destination already exists: {item.dst}",
            )
        )

    if item.src_mtime_ns is not None:
        actual_ns = os.stat(src_resolved).st_mtime_ns
        if actual_ns != item.src_mtime_ns:
            issues.append(
                OrganizeValidationIssue(
                    index=index,
                    code="mtime_mismatch",
                    message=f"Source changed since plan was generated: {item.src}",
                )
            )

    return issues


def _resolve_plan_path(workspace: str, rel_or_abs: str) -> str:
    raw = rel_or_abs
    if not os.path.isabs(raw):
        raw = os.path.join(workspace, raw)
    return os.path.realpath(os.path.expanduser(raw))


def _relative_to_workspace(workspace: str, path: str) -> str:
    resolved = _resolve_plan_path(workspace, path)
    ws_real = os.path.realpath(workspace)
    return os.path.relpath(resolved, ws_real)


def _path_within_scope(path: str, scope_resolved: str) -> bool:
    from myrm_agent_harness.core.security.path_security import is_within_boundary

    return is_within_boundary(path, scope_resolved)
