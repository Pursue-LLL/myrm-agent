#!/usr/bin/env python3
"""Refresh _ARCH.md file tables from directory listings (no placeholder rows).

Scans ``app/`` for ``_ARCH.md`` files that still contain placeholder markers
(``待补`` or ``（见目录）``) and rewrites the file table from on-disk sources.

Run from myrm-agent-server root::

    python3 scripts/sync_arch_file_tables.py
    python3 scripts/sync_arch_file_tables.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Only rewrite stub _ARCH files created with the bulk placeholder table row.
_STUB_ROW = "| （见目录） | — | 按文件名自解释 | ⚠️ 待补 |"
_SKIP_NAMES = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"})
_SOURCE_SUFFIXES = (".py", ".json", ".yaml", ".yml", ".toml", ".md")


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
    return "模块"


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
            role = _infer_role(src.name)
            lines.append(f"| `{src.name}` | {role} | 见源码 | ⚠️ 待补 |")
    lines.append("")
    return "\n".join(lines)


def _needs_refresh(content: str) -> bool:
    return _STUB_ROW in content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "app",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    app_root: Path = args.app_root.resolve()
    updated = 0
    for arch in sorted(app_root.rglob("_ARCH.md")):
        if any(p in _SKIP_NAMES for p in arch.parts):
            continue
        text = arch.read_text(encoding="utf-8")
        if not _needs_refresh(text):
            continue
        rel_title = str(arch.parent.relative_to(app_root)).replace("\\", "/")
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
