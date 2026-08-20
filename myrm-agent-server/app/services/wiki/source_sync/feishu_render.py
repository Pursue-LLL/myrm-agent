"""Feishu Docx blocks → Markdown rendering (pure functions, no I/O).

[INPUT]
- Feishu OpenAPI /docx/v1/documents/{id}/blocks payload (raw JSON)
- app.services.wiki.source_sync.feishu_render_inline (POS: inline element renderers)

[OUTPUT]
- feishu_docx_blocks_to_markdown: full docx block payload → GFM Markdown
- FEISHU_IMAGE_PREFIX / FEISHU_IMAGE_RE: image placeholder protocol shared with feishu.py

[POS]
Pure block→Markdown converter for Feishu docs. No I/O or state; image placeholders
are resolved by the caller (feishu.py) after download.
"""

from __future__ import annotations

import re

from app.services.wiki.source_sync.feishu_render_inline import (
    _as_elements,
    _decode_url,
    _escape_md,
    _plain_text,
    _render_elements,
)

# Docx block_type enum (Feishu OpenAPI, verified against official docs)
_BLOCK_TEXT = 2
_BLOCK_HEADING_MIN = 3  # heading1
_BLOCK_HEADING_MAX = 11  # heading9
_BLOCK_BULLET = 12
_BLOCK_ORDERED = 13
_BLOCK_CODE = 14
_BLOCK_QUOTE = 15
_BLOCK_TODO = 17
_BLOCK_CALLOUT = 19
_BLOCK_DIVIDER = 22
_BLOCK_FILE = 23
_BLOCK_IMAGE = 27
_BLOCK_LINK_PREVIEW = 48

_LIST_BLOCK_TYPES = frozenset({_BLOCK_BULLET, _BLOCK_ORDERED, _BLOCK_TODO})

# Structural block metadata that never carries renderable text elements.
_STRUCTURAL_KEYS = frozenset({"block_id", "block_type", "parent_id", "children"})

# Parent id used when a block has no parent_id (top-level document blocks).
_ROOT_PARENT = "<root>"

FEISHU_IMAGE_PREFIX = "feishu-image:"
FEISHU_IMAGE_RE = re.compile(rf"{FEISHU_IMAGE_PREFIX}([^\s)]+)")


def feishu_docx_blocks_to_markdown(payload: dict[str, object]) -> str | None:
    """Convert Feishu Docx blocks payload to Markdown.

    Unsupported block types degrade to their inline text. Nested list blocks
    (bullet/ordered/todo) are indented by walking the parent chain; ordered
    counters are scoped per list root so nested lists restart at 1.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None

    blocks = [b for b in items if isinstance(b, dict)]
    by_id = _index_blocks(blocks)
    ordered_serial = _assign_ordered_serials(blocks, by_id)

    groups: list[list[str]] = []
    current_group: list[str] | None = None
    fallback_serial = 0
    prev_was_ordered = False

    def flush() -> None:
        nonlocal current_group
        if current_group:
            groups.append(current_group)
            current_group = None

    def emit(line: str, *, compact: bool) -> None:
        nonlocal current_group
        if compact:
            if current_group is None:
                current_group = []
            current_group.append(line)
        else:
            flush()
            groups.append([line])

    for block in blocks:
        block_type = block.get("block_type")
        if not isinstance(block_type, int) or isinstance(block_type, bool):
            continue

        list_depth = _list_depth(block, by_id)

        if _BLOCK_HEADING_MIN <= block_type <= _BLOCK_HEADING_MAX:
            level = block_type - _BLOCK_HEADING_MIN + 1
            text = _block_text(block)
            if text:
                emit(f"{'#' * level} {text}", compact=False)
            continue

        if block_type == _BLOCK_TEXT:
            text = _block_text(block)
            if text:
                emit(f"{'  ' * list_depth}{text}", compact=list_depth > 0)
            continue

        if block_type == _BLOCK_BULLET:
            text = _block_text(block)
            if text:
                emit(f"{'  ' * list_depth}- {text}", compact=True)
            continue

        if block_type == _BLOCK_ORDERED:
            block_id = block.get("block_id")
            serial = ordered_serial.get(block_id) if isinstance(block_id, str) and block_id in ordered_serial else None
            if serial is None:
                if not prev_was_ordered:
                    fallback_serial = 0
                fallback_serial += 1
                serial = fallback_serial
                prev_was_ordered = True
            text = _block_text(block)
            if text:
                emit(
                    f"{'  ' * list_depth}{serial}. {text}",
                    compact=True,
                )
            continue
        prev_was_ordered = False

        if block_type == _BLOCK_CODE:
            rendered = _render_code_block(block)
            if rendered:
                emit(rendered, compact=False)
            continue

        if block_type in (_BLOCK_QUOTE, _BLOCK_CALLOUT):
            text = _block_text(block)
            if text:
                emit(f"{'> ' * (list_depth + 1)}{text}", compact=list_depth > 0)
            continue

        if block_type == _BLOCK_TODO:
            text = _block_text(block)
            if text:
                done = _todo_done(block)
                emit(
                    f"{'  ' * list_depth}- [{'x' if done else ' '}] {text}",
                    compact=True,
                )
            continue

        if block_type == _BLOCK_DIVIDER:
            emit("---", compact=False)
            continue

        if block_type == _BLOCK_FILE:
            rendered = _render_file_block(block)
            if rendered:
                emit(rendered, compact=False)
            continue

        if block_type == _BLOCK_IMAGE:
            token = _image_token(block)
            if token:
                emit(f"![image]({FEISHU_IMAGE_PREFIX}{token})", compact=False)
            continue

        if block_type == _BLOCK_LINK_PREVIEW:
            rendered = _render_link_preview(block)
            if rendered:
                emit(rendered, compact=False)
            continue

        # Unmapped block types (tables/bitable/grids etc.) → best-effort text
        text = _block_text(block)
        if text:
            emit(f"{'  ' * list_depth}{text}", compact=False)

    flush()
    body = "\n\n".join("\n".join(g) for g in groups).strip()
    return body or None


def _index_blocks(blocks: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Map block_id → block for parent-chain lookups."""
    indexed: dict[str, dict[str, object]] = {}
    for block in blocks:
        block_id = block.get("block_id")
        if isinstance(block_id, str) and block_id:
            indexed[block_id] = block
    return indexed


def _list_depth(block: dict[str, object], by_id: dict[str, dict[str, object]]) -> int:
    """Return the nested-list indent depth by walking the parent chain.

    Every list-typed ancestor (bullet/ordered/todo) adds one level of
    indentation, so a bullet inside a bullet inside a top-level list has
    depth 2.
    """
    depth = 0
    parent_id = block.get("parent_id")
    visited: set[str] = set()
    while isinstance(parent_id, str) and parent_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            break
        if _is_list_block(parent):
            depth += 1
        parent_id = parent.get("parent_id")
    return depth


def _is_list_block(block: dict[str, object]) -> bool:
    block_type = block.get("block_type")
    return isinstance(block_type, int) and block_type in _LIST_BLOCK_TYPES


def _assign_ordered_serials(blocks: list[dict[str, object]], by_id: dict[str, dict[str, object]]) -> dict[str, int]:
    """Assign sequential numbers to ordered blocks within each list group.

    A list group is the set of consecutive ordered siblings under the same
    parent (Feishu numbers them from 1). Nested ordered blocks under a list
    item form their own group. Sibling order comes from the parent's
    ``children`` array when available, otherwise from traversal order.
    """
    serials: dict[str, int] = {}
    by_parent: dict[str, list[dict[str, object]]] = {}
    for block in blocks:
        parent_id = block.get("parent_id")
        key = str(parent_id) if isinstance(parent_id, str) and parent_id else _ROOT_PARENT
        by_parent.setdefault(key, []).append(block)

    for key, siblings in by_parent.items():
        order: list[dict[str, object]] = []
        if key != _ROOT_PARENT:
            parent = by_id.get(key)
            children = parent.get("children") if parent else None
            if isinstance(children, list):
                child_map = {b.get("block_id"): b for b in siblings if isinstance(b.get("block_id"), str)}
                order = [child_map[c] for c in children if c in child_map]
        if not order:
            order = siblings

        run = 0
        for block in order:
            block_type = block.get("block_type")
            if not isinstance(block_type, int) or block_type != _BLOCK_ORDERED:
                run = 0
                continue
            run += 1
            block_id = block.get("block_id")
            if isinstance(block_id, str):
                serials[block_id] = run
    return serials


def _block_text(block: dict[str, object]) -> str:
    """Extract text from the first field that carries renderable elements.

    Walks the block's content fields (any key besides structural metadata) so
    newly introduced Feishu block types with elements are covered without a
    field-name allowlist.
    """
    for key, section in block.items():
        if key in _STRUCTURAL_KEYS:
            continue
        if isinstance(section, dict) and isinstance(section.get("elements"), list):
            rendered = _render_elements(section.get("elements"))
            if rendered:
                return rendered
    return ""


def _render_code_block(block: dict[str, object]) -> str:
    section = block.get("code")
    if not isinstance(section, dict):
        return ""
    lang = section.get("language", "")
    language = str(lang).strip() if isinstance(lang, str) else ""
    code = "".join(_plain_text(element) for element in _as_elements(section.get("elements")))
    # A fence must be longer than any backtick run inside the code, else the
    # code block terminates early (e.g. embedded markdown documents).
    max_run = max((len(m) for m in re.findall(r"`+", code)), default=0)
    fence = "`" * max(3, max_run + 1)
    trailing = "" if code.endswith("\n") else "\n"
    return f"{fence}{language}\n{code}{trailing}{fence}"


def _todo_done(block: dict[str, object]) -> bool:
    section = block.get("todo")
    return bool(section.get("done")) if isinstance(section, dict) else False


def _image_token(block: dict[str, object]) -> str:
    section = block.get("image")
    if not isinstance(section, dict):
        return ""
    raw = section.get("token")
    return raw.strip() if isinstance(raw, str) else ""


def _render_file_block(block: dict[str, object]) -> str:
    """Render a Feishu file block (video/attachment) by its display name."""
    section = block.get("file")
    if not isinstance(section, dict):
        return ""
    raw = section.get("name")
    name = raw.strip() if isinstance(raw, str) else ""
    return f"文件: {_escape_md(name)}" if name else "文件"


def _render_link_preview(block: dict[str, object]) -> str:
    section = block.get("link_preview")
    if not isinstance(section, dict):
        return ""
    raw_url = section.get("url")
    raw_title = section.get("title")
    url = _decode_url(raw_url)
    title = raw_title if isinstance(raw_title, str) else ""
    title = title.strip()
    if url:
        return f"[{_escape_md(title or url)}](<{url}>)"
    if title:
        return title
    return ""


__all__ = [
    "FEISHU_IMAGE_PREFIX",
    "FEISHU_IMAGE_RE",
    "feishu_docx_blocks_to_markdown",
]
