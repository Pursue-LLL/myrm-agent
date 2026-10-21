"""Canonical memory import warning vocabulary (single source of truth).

[INPUT]
None (pure definitions).

[OUTPUT]
ImportWarningCode: strict union of every warning code the memory import pipeline
can attach to a dry-run result; IMPORT_WARNING_CODES: runtime view of the union.

[POS]
Shared contract leaf of the schemas layer. Import adapters emit these codes, the
migration wizard and the import review dialog resolve them through the
``memory.importWarnings`` namespace, and the contract tests guard both
directions: every emitted code must be declared here, and every declared code
must carry copy in all six product locales.
"""

from __future__ import annotations

from typing import Literal, get_args

ImportWarningCode = Literal[
    # Native / Myrm archive
    "no_native_buckets",
    "myrm_archive_memory_section_missing",
    "myrm_archive_non_memory_sections_review_only",
    # agentmemory
    "agentmemory_version_unsupported",
    "agentmemory_too_many_sessions",
    "agentmemory_too_many_memories",
    "agentmemory_too_many_summaries",
    "agentmemory_too_many_observations",
    "agentmemory_graph_skipped",
    "agentmemory_access_logs_skipped",
    # Coding agents
    "claude_code_no_lines",
    "claude_code_too_many_lines",
    "claude_code_too_many_entries",
    "claude_code_no_conversation_entries",
    "codex_empty_payload",
    "cursor_empty_payload",
    "hermes_api_keys_detected",
    "hermes_skills_detected",
    "openclaw_skills_detected",
    # Third-party exports
    "chatgpt_no_conversations",
    "gemini_no_conversations",
    "gbrain_no_pages",
    "mem0_no_memories_found",
    "trae_empty_payload",
    "windsurf_empty_payload",
    # PLUR
    "plur_no_engrams_found",
    "plur_inactive_skipped",
    "plur_invalid_engrams",
    # Paste lane
    "pasted_empty",
    "pasted_text_too_large",
    "pasted_entries_over_limit",
    "pasted_model_extraction_failed",
    # Fallback
    "unsupported_source",
]

IMPORT_WARNING_CODES: tuple[str, ...] = tuple(get_args(ImportWarningCode))
