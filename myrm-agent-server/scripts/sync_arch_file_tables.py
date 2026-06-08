#!/usr/bin/env python3
"""Refresh _ARCH.md file tables from directory listings and file-header POS markers.

Scans ``app/`` for ``_ARCH.md`` files that contain stub markers (``待补`` or
``（见目录）``) and rewrites the file table from on-disk sources.

Run from myrm-agent-server root::

    python3 scripts/sync_arch_file_tables.py
    python3 scripts/sync_arch_file_tables.py --path-prefix api/
    python3 scripts/sync_arch_file_tables.py --dry-run
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_SKIP_NAMES = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"})
_SOURCE_SUFFIXES = (".py", ".json", ".yaml", ".yml", ".toml", ".md")
_STUB_MARKERS = ("待补", "（见目录）")
_POS_PATTERNS = (
    re.compile(r"@pos:\s*(.+)", re.IGNORECASE),
    re.compile(r"\[POS\]\s*\n?\s*(.+)", re.IGNORECASE),
    re.compile(r"@pos\s+(.+)", re.IGNORECASE),
)
_HEADER_SCAN_LINES = 25


def _parent_arch_href(arch_path: Path, app_root: Path) -> str:
    rel = arch_path.parent.relative_to(app_root)
    depth = len(rel.parts)
    if depth == 0:
        return "_ARCH.md"
    return "/".join([".."] * depth) + "/_ARCH.md"


def _list_sources(directory: Path) -> list[Path]:
    items: list[Path] = []
    for child in sorted(directory.iterdir()):
        if not child.is_file():
            continue
        if child.name == "_ARCH.md":
            continue
        if child.suffix in _SOURCE_SUFFIXES or child.name in {"__init__.py", "router.py"}:
            items.append(child)
    return items


def _infer_role(name: str) -> str:
    if name == "__init__.py":
        return "入口"
    if name == "router.py" or name.endswith("_routes.py"):
        return "路由"
    if name.endswith(".json"):
        return "数据"
    if name.startswith("test_"):
        return "测试"
    return "模块"


def _extract_pos(py_path: Path) -> str | None:
    if py_path.suffix != ".py":
        return None
    head = "\n".join(py_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES])
    for pattern in _POS_PATTERNS:
        match = pattern.search(head)
        if match:
            pos = match.group(1).strip().rstrip(".")
            if pos:
                return pos[:120]
    return None


def _has_io_header(py_path: Path) -> bool:
    if py_path.suffix != ".py":
        return False
    head = "\n".join(py_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES])
    return bool(re.search(r"(\[POS\]|\[INPUT\]|@pos:|@input:)", head, re.IGNORECASE))


def _describe_source(src: Path) -> tuple[str, str, str]:
    role = _infer_role(src.name)
    pos = _extract_pos(src)
    if pos:
        return role, pos, "✅"
    if src.suffix == ".py" and _has_io_header(src):
        return role, "见文件头 I/O/P", "✅"
    if src.suffix == ".py":
        return role, "见源码", "—"
    return role, "静态配置/文档", "—"


def _build_arch(rel_title: str, parent_href: str, sources: list[Path]) -> str:
    lines = [
        f"# {rel_title}/",
        "",
        "## 架构概述",
        "",
        f"本目录模块说明。上级文档：[{parent_href}]({parent_href})。",
        "",
        "## 文件清单",
        "",
        "| 文件 | 地位 | 职责 | I/O/P |",
        "|------|------|------|-------|",
    ]
    if not sources:
        lines.append("| — | — | 空目录或仅子目录 | — |")
    else:
        for src in sources:
            role, duty, iop = _describe_source(src)
            lines.append(f"| `{src.name}` | {role} | {duty} | {iop} |")
    lines.append("")
    return "\n".join(lines)


def _needs_refresh(content: str) -> bool:
    return any(marker in content for marker in _STUB_MARKERS)


def _matches_prefix(rel: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    normalized = rel.replace("\\", "/")
    return any(normalized == p.rstrip("/") or normalized.startswith(p) for p in prefixes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "app",
    )
    parser.add_argument(
        "--path-prefix",
        action="append",
        default=[],
        help="Only refresh _ARCH.md under this app-relative prefix (repeatable).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    app_root: Path = args.app_root.resolve()
    prefixes = tuple(args.path_prefix)
    updated = 0
    for arch in sorted(app_root.rglob("_ARCH.md")):
        if any(p in _SKIP_NAMES for p in arch.parts):
            continue
        rel_title = str(arch.parent.relative_to(app_root)).replace("\\", "/")
        if not _matches_prefix(rel_title, prefixes):
            continue
        text = arch.read_text(encoding="utf-8")
        if not _needs_refresh(text):
            continue
        parent_href = _parent_arch_href(arch, app_root)
        sources = _list_sources(arch.parent)
        new_text = _build_arch(rel_title, parent_href, sources)
        if args.dry_run:
            print(f"would update: {arch.relative_to(app_root.parent)}")
        else:
            arch.write_text(new_text, encoding="utf-8")
            print(f"updated: {arch.relative_to(app_root.parent)}")
        updated += 1

    print(f"done ({updated} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
