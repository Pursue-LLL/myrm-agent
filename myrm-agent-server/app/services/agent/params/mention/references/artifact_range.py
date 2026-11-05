"""[INPUT]
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- artifact_range_part: @artifact-selection handler

[POS]
Artifact-selection @ references. The selection text is produced by the UI and passed through
untouched; only its byte size is budgeted here.
"""

from __future__ import annotations

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _can_inline, _format_size, _xml_error, _xml_metadata, _xml_part


async def artifact_range_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    base_display = ref.label or "artifact"
    display = f"{base_display} ({ref.range})" if ref.range else base_display
    if not ref.content:
        ctx.parts.append(_xml_error(display, "empty selection"))
        return
    selection_bytes = len(ref.content.encode("utf-8"))
    if _can_inline(selection_bytes, ctx.total_bytes):
        ctx.parts.append(_xml_part(display, "artifact-range", ref.content))
        ctx.total_bytes += selection_bytes
    else:
        ctx.parts.append(
            _xml_metadata(
                display,
                "artifact-range",
                f"Selection too large ({_format_size(selection_bytes)})",
            )
        )
