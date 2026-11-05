"""[INPUT]
- ...models::MentionReferenceRequest (POS: structured @ reference DTO)
- .pipeline::_build_mention_reference_context (POS: reference expansion pipeline)

[OUTPUT]
- _text_reference_to_structured: legacy plain-text @ token → structured reference
- _build_mentioned_file_context: expand plain-text @ tokens into prompt context

[POS]
Compatibility entry for the plain-text mention form (`@file.py:10-20`, `@staged`, `@diff`,
`@codebase`, `@folder:…`, `@url:…`). The GUI sends structured references; this adapter keeps the
text form on the same pipeline instead of a second implementation.
"""

from __future__ import annotations

import re

from ..models import MentionReferenceRequest
from .pipeline import _build_mention_reference_context

_LINE_RANGE_PATTERN = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")


def _text_reference_to_structured(ref: str) -> MentionReferenceRequest:
    if ref == "@staged":
        return MentionReferenceRequest(type="git_staged", label="@staged")
    if ref == "@diff":
        return MentionReferenceRequest(type="git_diff", label="@diff")
    if ref == "@codebase":
        return MentionReferenceRequest(type="codebase", label="@codebase")
    if ref.startswith("@folder:"):
        path = ref.removeprefix("@folder:")
        return MentionReferenceRequest(type="workspace_folder", path=path or ".", label=ref)
    if ref.startswith("@url:"):
        url = ref.removeprefix("@url:")
        return MentionReferenceRequest(type="url", url=url, label=ref)

    match = _LINE_RANGE_PATTERN.match(ref)
    if match:
        path, start_raw, end_raw = match.groups()
        start_line = int(start_raw)
        end_line = int(end_raw) if end_raw else start_line
        if end_line < start_line:
            start_line, end_line = end_line, start_line
        return MentionReferenceRequest(
            type="workspace_file",
            path=path,
            label=ref,
            start_line=start_line,
            end_line=end_line,
        )
    return MentionReferenceRequest(type="workspace_file", path=ref, label=ref)


async def _build_mentioned_file_context(
    mentioned_files: list[str],
    workspace_dir: str,
    max_context_tokens: int | None = None,
) -> tuple[str, list[str], int]:
    structured = [_text_reference_to_structured(ref) for ref in mentioned_files]
    return await _build_mention_reference_context(structured, workspace_dir, max_context_tokens)
