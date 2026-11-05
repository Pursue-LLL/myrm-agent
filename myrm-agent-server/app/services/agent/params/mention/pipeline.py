"""[INPUT]
- ...models::MentionReferenceRequest / MultimodalQuery (POS: request DTOs)
- .context::MentionContext (POS: per-turn accumulation state)
- .references::HANDLERS (POS: reference type → handler registry)
- .xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _build_mention_reference_context: expand the structured references into one prompt context block
- _inject_mentioned_files_into_query: append that block to the user query

[POS]
The @-mention pipeline. This is the only place that knows the dispatch order and the token budget;
handlers only produce fragments and report their byte cost, so a policy change stays in one file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import MentionReferenceRequest, MultimodalQuery
from .context import MentionContext
from .references import HANDLERS
from .xml import _xml_error

logger = logging.getLogger(__name__)

_MENTION_MAX_FILES = 10


async def _build_mention_reference_context(
    mention_references: list[MentionReferenceRequest],
    workspace_dir: str,
    max_context_tokens: int | None = None,
    agent_id: str | None = None,
) -> tuple[str, list[str], int]:
    """Read structured GUI @ references and build prompt context."""

    from myrm_agent_harness.utils.text_utils import get_token_count

    workspace_real = str(Path(workspace_dir).expanduser().resolve())
    context = MentionContext(workspace_real=workspace_real, agent_id=agent_id)

    # Token budget limits (25% soft, 50% hard)
    soft_limit = int(max_context_tokens * 0.25) if max_context_tokens else 999_999_999
    hard_limit = int(max_context_tokens * 0.50) if max_context_tokens else 999_999_999

    for ref in mention_references[:_MENTION_MAX_FILES]:
        handler = HANDLERS.get(ref.type)
        if handler is None:
            context.parts.append(_xml_error(ref.label or ref.type, "unsupported reference"))
            continue
        await handler(ref, context)

    if not context.parts:
        return "", [], 0

    final_content = "\n\n<mentioned_files>\n" + "\n".join(context.parts) + "\n</mentioned_files>"
    total_tokens = get_token_count(final_content)

    if total_tokens > hard_limit:
        context.warnings.append(
            f"Context size {total_tokens} tokens exceeds 50% limit ({hard_limit} tokens), some references may have been truncated"
        )
    elif total_tokens > soft_limit:
        context.warnings.append(f"Warning: Context size {total_tokens} tokens exceeds 25% soft limit ({soft_limit} tokens)")

    return final_content, context.warnings, total_tokens


def _inject_mentioned_files_into_query(
    query: MultimodalQuery,
    context: str,
) -> MultimodalQuery:
    """Append mentioned file context to the user query."""
    if not context:
        return query
    if isinstance(query, str):
        return query + context
    for part in query:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            part["text"] = str(part["text"]) + context
            return query
    query.append({"type": "text", "text": context})
    return query
