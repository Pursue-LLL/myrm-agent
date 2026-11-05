"""[INPUT]
- .pipeline::enrich_query (POS: server-side query context blocks)
- .archive_restore (POS: typed archive restore validation and prompt materialization)
- .upload_sync (POS: uploaded file workspace sync + RAG routing)

[OUTPUT]
- enrich_query / EnrichedQuery
- archive restore: ArchiveRestoreRequestError, prevalidate_archive_restore_actions,
  build_archive_restore_action_context_with_results, inject_archive_restore_actions_into_query
- upload sync: sync_uploaded_files_to_workspace, inject_uploaded_files_into_query

[POS]
Aggregate exit of the message-enrichment domain. Everything that turns the raw user message into the
final query (mentions, uploads, restore actions, @agent directives, /learn rewrite, spillover) is
reachable from here; `converter.py` calls only this facade.
"""

from __future__ import annotations

from .archive_restore import (
    ArchiveRestoreRequestError,
    build_archive_restore_action_context_with_results,
    inject_archive_restore_actions_into_query,
    prevalidate_archive_restore_actions,
)
from .pipeline import EnrichedQuery, enrich_query
from .upload_sync import (
    inject_uploaded_files_into_query,
    sync_uploaded_files_to_workspace,
)

__all__ = [
    "ArchiveRestoreRequestError",
    "EnrichedQuery",
    "build_archive_restore_action_context_with_results",
    "enrich_query",
    "inject_archive_restore_actions_into_query",
    "inject_uploaded_files_into_query",
    "prevalidate_archive_restore_actions",
    "sync_uploaded_files_to_workspace",
]
