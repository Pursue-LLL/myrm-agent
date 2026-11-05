"""[INPUT]
- .artifact_range::artifact_range_part (POS: @artifact-selection handler)
- .codebase::codebase_part (POS: @codebase handler)
- .folder::workspace_folder_part (POS: @folder handler)
- .git::git_staged_part / git_diff_part (POS: @staged / @diff handlers)
- .prior_chat::prior_chat_part (POS: @chat: handler)
- .stored_file::stored_file_part (POS: @uploaded / @generated handler)
- .url::url_part (POS: @url: handler)
- .wiki::wiki_concept_part / wiki_raw_file_part (POS: @wiki: handlers)
- .workspace_file::workspace_file_part (POS: @file handler)

[OUTPUT]
- HANDLERS: reference type → async handler, in the pipeline's dispatch order

[POS]
Aggregate exit of the reference handlers. One module per reference type; the registry is the only
place that knows the type strings, so adding a reference type is one module + one registry line.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ...models import MentionReferenceRequest
from ..context import MentionContext
from .artifact_range import artifact_range_part
from .codebase import codebase_part
from .folder import workspace_folder_part
from .git import git_diff_part, git_staged_part
from .prior_chat import prior_chat_part
from .stored_file import stored_file_part
from .url import url_part
from .wiki import wiki_concept_part, wiki_raw_file_part
from .workspace_file import workspace_file_part

MentionHandler = Callable[[MentionReferenceRequest, MentionContext], Awaitable[None]]

HANDLERS: dict[str, MentionHandler] = {
    "git_staged": git_staged_part,
    "git_diff": git_diff_part,
    "workspace_folder": workspace_folder_part,
    "url": url_part,
    "workspace_file": workspace_file_part,
    "uploaded_file": stored_file_part,
    "generated_file": stored_file_part,
    "codebase": codebase_part,
    "wiki_concept": wiki_concept_part,
    "wiki_raw_file": wiki_raw_file_part,
    "prior_chat": prior_chat_part,
    "artifact_range": artifact_range_part,
}

__all__ = ["HANDLERS", "MentionHandler"]
