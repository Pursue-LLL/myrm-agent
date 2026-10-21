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
_MODULE_DOC_PATTERN = re.compile(r'^[\s\S]*?"""([^"]{8,})', re.MULTILINE)
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
    head = py_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES]
    block: list[str] = []
    in_block = False
    for line in head:
        if re.match(r"^\s*(\[POS\]|@pos:)", line, re.IGNORECASE):
            inline = re.sub(r"^\s*(\[POS\]|@pos:)\s*", "", line, flags=re.IGNORECASE).strip()
            if inline:
                block.append(inline.rstrip(":").rstrip("."))
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if not stripped:
                break
            if stripped.startswith("-") or stripped.startswith("*"):
                break
            block.append(stripped.rstrip(":").rstrip("."))
    if block:
        sentence = " ".join(block)
        if sentence.endswith(":"):
            sentence = sentence[:-1].rstrip()
        period_idx = sentence.find(". ")
        if period_idx != -1:
            sentence = sentence[: period_idx + 1]
        return sentence[:160]
    return None


def _extract_output(py_path: Path) -> str | None:
    if py_path.suffix != ".py":
        return None
    head = py_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES]
    block: list[str] = []
    in_block = False
    for line in head:
        if re.match(r"^\s*(\[OUTPUT\]|@output:)", line, re.IGNORECASE):
            inline = re.sub(r"^\s*(\[OUTPUT\]|@output:)\s*", "", line, flags=re.IGNORECASE).strip()
            if inline:
                block.append(inline.rstrip(":").rstrip("."))
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if not stripped:
                break
            if stripped.startswith("-") or stripped.startswith("*"):
                break
            block.append(stripped.rstrip(":").rstrip("."))
    if block:
        return " ".join(block)[:160]
    return None


def _extract_module_summary(py_path: Path) -> str | None:
    if py_path.suffix != ".py":
        return None
    text = py_path.read_text(encoding="utf-8")
    match = _MODULE_DOC_PATTERN.match(text)
    if not match:
        return None
    first_line = match.group(1).strip().splitlines()[0].strip()
    if len(first_line) < 8:
        return None
    return first_line[:160]


def _has_io_header(py_path: Path) -> bool:
    if py_path.suffix != ".py":
        return False
    head = "\n".join(py_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES])
    return bool(re.search(r"(\[POS\]|\[INPUT\]|@pos:|@input:)", head, re.IGNORECASE))


def _fallback_py_duty(name: str) -> str:
    stem = Path(name).stem
    if stem == "router":
        return "HTTP 路由处理器"
    if stem == "__init__":
        return "包入口与导出"
    if stem.endswith("_routes"):
        return "路由子模块"
    return f"{stem} 模块实现"


def _describe_source(src: Path) -> tuple[str, str, str]:
    role = _infer_role(src.name)
    pos = _extract_pos(src)
    if pos:
        return role, pos, "✅"
    output = _extract_output(src)
    if output:
        return role, output, "✅"
    summary = _extract_module_summary(src)
    if summary:
        return role, summary, "✅"
    if src.suffix == ".py" and _has_io_header(src):
        return role, "见文件头 I/O/P", "✅"
    if src.suffix == ".py":
        return role, _fallback_py_duty(src.name), "—"
    return role, "静态配置/文档", "—"


def _build_arch(rel_title: str, parent_href: str, sources: list[Path]) -> str:
    lines = [
        f"# {rel_title}/",
        "",
        "## 架构概述",
        "",
        f"{rel_title} 模块。上级文档：[{parent_href}]({parent_href})。",
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


def _has_substantive_overview(content: str) -> bool:
    """Skip auto-rewrite when _ARCH already has a multi-line architecture section."""
    if "## 架构概述" not in content:
        return False
    _, _, tail = content.partition("## 架构概述")
    section, _, _ = tail.partition("## ")
    body = section.strip()
    if not body:
        return False
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return True
    return len(lines[0]) > 80


def _has_curated_file_table(content: str) -> bool:
    """True when the file table mixes stub markers with completed I/O/P or extra sections."""
    in_table = False
    for line in content.splitlines():
        if line.startswith("|") and "I/O/P" in line:
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if any(marker in line for marker in _STUB_MARKERS):
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 5:
                iop = cells[-2]
                if iop in {"✅", "—", "-"}:
                    return True
    if content.count("## ") > 2:
        return True
    return False


def _needs_refresh(content: str, force: bool) -> bool:
    if force:
        return True
    if not any(marker in content for marker in _STUB_MARKERS):
        return False
    if _has_substantive_overview(content):
        return False
    if _has_curated_file_table(content):
        return False
    return True


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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite matched _ARCH.md even when no stub markers remain.",
    )
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
        if not _needs_refresh(text, args.force):
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
