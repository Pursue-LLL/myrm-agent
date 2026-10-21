"""Rewrite Obsidian-style wikilinks after file moves.

[INPUT]
- workspace 根路径 + moved_files (src,dst) 绝对路径对

[OUTPUT]
- rewrite_wikilinks_in_tree: 扫描 workspace 内 *.md 并重写 [[wikilink]] 目标

[POS]
Apply/rollback 后的 Obsidian 双链一致性维护。stem 与相对路径双映射。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(#[^\]|]+)?(\|[^\]]+)?\]\]")


def rewrite_wikilinks_in_tree(workspace: str, moved_files: list[tuple[str, str]]) -> int:
    """Update [[wikilink]] targets in markdown files under workspace. Returns files updated."""
    if not moved_files:
        return 0

    ws = Path(os.path.realpath(os.path.expanduser(workspace)))
    path_map: dict[str, str] = {}
    for src, dst in moved_files:
        src_rel = _as_posix_relpath(ws, src)
        dst_rel = _as_posix_relpath(ws, dst)
        src_stem = Path(src_rel).stem
        dst_stem = Path(dst_rel).stem
        path_map[src_rel] = dst_rel
        path_map[src_stem] = dst_stem

    updated = 0
    for md_path in ws.rglob("*.md"):
        if not md_path.is_file():
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text = _rewrite_text(text, path_map)
        if new_text != text:
            md_path.write_text(new_text, encoding="utf-8")
            updated += 1
    return updated


def _rewrite_text(text: str, path_map: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        mapped = path_map.get(target)
        if mapped is None:
            mapped = path_map.get(Path(target).stem)
        if mapped is None:
            return match.group(0)
        suffix = (match.group(2) or "") + (match.group(3) or "")
        display = Path(mapped).stem if "/" not in mapped and "\\" not in mapped else mapped
        return f"[[{display}{suffix}]]"

    return _WIKILINK_RE.sub(repl, text)


def _as_posix_relpath(workspace: Path, path: str) -> str:
    resolved = Path(os.path.realpath(os.path.expanduser(path)))
    return resolved.relative_to(workspace).as_posix()
