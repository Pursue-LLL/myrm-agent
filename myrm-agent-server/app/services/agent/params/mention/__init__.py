"""[INPUT]
- .pipeline::_build_mention_reference_context / _inject_mentioned_files_into_query (POS: @-mention pipeline)
- .text_references::_text_reference_to_structured / _build_mentioned_file_context (POS: plain-text @ adapter)
- .references (POS: one handler per reference type)
- .documents (POS: Office parsing + file classification)
- .xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- The public @-mention API consumed by the request conversion layer: context building, query
  injection, the plain-text adapter, and the direct references the existing tests exercise.

[POS]
Aggregate exit of the @-mention subpackage. Callers keep importing `params.mention` and see the same
names as before; the implementation lives in the pipeline, the reference handlers and the shared
document/XML helpers behind it.
"""

from __future__ import annotations

from .context import MentionContext
from .documents import (
    _BINARY_EXTENSIONS,
    _DOCUMENT_EXTENSIONS,
    _parse_document,
    _parse_stored_document,
)
from .pipeline import _MENTION_MAX_FILES, _build_mention_reference_context, _inject_mentioned_files_into_query
from .references.codebase import _build_codebase_overview, _codebase_overview_part
from .references.folder import _get_folder_tree
from .references.git import _get_git_staged_diff
from .references.prior_chat import (
    _MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE,
    _load_prior_chat_document,
    _prior_chat_part,
)
from .references.stored_file import _stored_file_part
from .references.url import _fetch_url_content
from .references.wiki import _wiki_concept_part, _wiki_raw_file_part
from .references.workspace_file import _read_file_lines, _workspace_file_part
from .text_references import _build_mentioned_file_context, _text_reference_to_structured
from .xml import (
    _MENTION_MAX_INLINE_BYTES,
    _MENTION_MAX_TOTAL_BYTES,
    _can_inline,
    _format_size,
    _xml_error,
    _xml_metadata,
    _xml_part,
)

__all__ = [
    "MentionContext",
    "_BINARY_EXTENSIONS",
    "_DOCUMENT_EXTENSIONS",
    "_MENTION_MAX_FILES",
    "_MENTION_MAX_INLINE_BYTES",
    "_MENTION_MAX_TOTAL_BYTES",
    "_MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE",
    "_build_codebase_overview",
    "_build_mention_reference_context",
    "_build_mentioned_file_context",
    "_can_inline",
    "_codebase_overview_part",
    "_fetch_url_content",
    "_format_size",
    "_get_folder_tree",
    "_get_git_staged_diff",
    "_inject_mentioned_files_into_query",
    "_load_prior_chat_document",
    "_parse_document",
    "_parse_stored_document",
    "_prior_chat_part",
    "_read_file_lines",
    "_stored_file_part",
    "_text_reference_to_structured",
    "_wiki_concept_part",
    "_wiki_raw_file_part",
    "_workspace_file_part",
    "_xml_error",
    "_xml_metadata",
    "_xml_part",
]
