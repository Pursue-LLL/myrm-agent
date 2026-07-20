"""Parse text responses returned by the Chrome DevTools MCP server."""

from __future__ import annotations

import json
import re

_PAGE_RE = re.compile(r"^(?:Page\s+(?:idx\s+)?)?(\d+)\s*:", re.MULTILINE)
_TARGET_RE = re.compile(r"Myrm exact targetId:\s*([A-Za-z0-9-]+)")
_JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)


def text_content(result: dict[str, object]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    blocks: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            value = item.get("text")
            if isinstance(value, str):
                blocks.append(value)
    return "\n".join(blocks)


def parse_new_page(result: dict[str, object]) -> tuple[int, str]:
    text = text_content(result)
    page_matches = _PAGE_RE.findall(text)
    target_match = _TARGET_RE.search(text)
    if not page_matches or target_match is None:
        raise RuntimeError(
            f"MCP new_page did not return pageId + exact targetId: {text[:500]}"
        )
    return int(page_matches[-1]), target_match.group(1)


def _coerce_parsed_json_value(value: object) -> object:
    """Unwrap MCP evaluate payloads that stringify JSON objects."""
    if not isinstance(value, str):
        return value
    nested = value.strip()
    if not nested.startswith("{") and not nested.startswith("["):
        return value
    try:
        return json.loads(nested)
    except json.JSONDecodeError:
        return value


def parse_evaluate_result(result: dict[str, object]) -> object:
    text = text_content(result)
    match = _JSON_FENCE_RE.search(text)
    candidate = match.group(1).strip() if match is not None else text.strip()
    if candidate.startswith("Script ran on page and returned:"):
        candidate = candidate.split(":", maxsplit=1)[1].strip()
    try:
        return _coerce_parsed_json_value(json.loads(candidate))
    except json.JSONDecodeError:
        return candidate

