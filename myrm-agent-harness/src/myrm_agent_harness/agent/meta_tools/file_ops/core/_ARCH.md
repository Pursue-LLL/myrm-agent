# core/

## Overview
Text Editor core business logic module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Text Editor core business logic module. | — |
| archive_restore_guard.py | Core | Archive restore read guard. Blocks oversized full archive restores before loading contents, formats structured blocked payloads, and parses that payload for runtime status events. | ✅ |
| batch_str_replace.py | Core | Batch str-replace engine. In-memory sequential apply with overlap precheck before single disk write. An `old_str` matches the file's own text, exactly or apart from whitespace, indentation and escapes (`CONTENT_PRESERVING_MIN_CONFIDENCE`); a block that only shares its first and last line is refused with the closest real lines shown, so an edit never replaces lines the caller did not write. Matching runs on LF text and the file's own line endings are written back, so a multi-line `old_str` written with LF matches a CRLF file and the file stays CRLF. | ✅ |
| file_conflict_guard.py | Core | File edit conflict guard. Calculates affected line ranges and blocks overlapping concurrent subagent edits. | ✅ |
| file_path_lock_manager.py | Core | Per-path asyncio lock manager for write serialization (canonical realpath+normcase identity; same file aliases serialize, disjoint paths parallel). | ✅ |
| file_operation_service.py | Core | File operation service: dispatches VIEW to `FileViewService` and runs CREATE / STR_REPLACE under the per-path lock; CREATE only creates (an existing path is refused in validation) and notifies created; Office text-write warnings on CREATE, vault markdown FM preserve + Office warnings on STR_REPLACE; anchors CAS version checks with edit target candidates for centered conflict rebasing; a verify command that exits non-zero undoes the write (`verify_runner.py`); one that never ran leaves it in place and says so. | ✅ |
| file_view_service.py | Core | VIEW operation: bounded-concurrency reads of files (optionally a line range) and directory listings; archive context reads enforce session ownership, pre-read full-restore budgets, range-aware restore budgets, and structured blocked payloads before exposing content; a full read records its content with the integrity guard and a range read records a partial marker. | ✅ |
| operation_context.py | Core | Provides OperationType, ViewRange, OperationContext. | ✅ |
| read_semaphore.py | Core | Event-loop scoped read semaphore registry for concurrent file read limits. | ✅ |
| result_formatter.py | Core | Provides FileContent, DirectoryListing, ResultFormatter. A line over the per-line cap is clamped with a marker, except in a file the context guard parked (see `parked_file_view.py`), where it is split into rows and a one-line notice says row numbers then count rows. | ✅ |
| verify_runner.py | Core | Post-write checks of the file tools: `run_verify_command` runs the model's `verify_command` from the workspace root and tells a command that judged the file (passed / exited non-zero) from one that never ran (refused by the command safety check, or the executor raised): only the first undoes the write, the second keeps it and the response says nothing was checked. `workspace_command_context` is the context every check command runs in (shared with the auto-verify linters). | ✅ |
| file_integrity_guard.py | Core | File integrity guard. Read-before-write gate (hard reject), full-read gate before edits, and content-hash version gate with two-tier anchor locator (exact match + signature line fallback) and candidate sequence support for context-centered self-healing preview payload on external modification; advances known hash on conflict rejection to eliminate infinite CAS rejection loops and guarantee 1-turn direct rebase. Agent-aware with per-agent tracking. One guard per executor, held weakly by the executor itself, so it is released with the executor and a new executor never inherits the records of a dead one. Partial reads use a sentinel marker. Masked write-back gate (`raise_if_masked_writeback`) refuses an edit whose new content carries a mask the redactor shows in place of a secret (`api_key: sk-pro...7890`, `DB_PASSWORD=***`) more often than the file does, because text copied from a masked read would otherwise replace the real value with the mask; fragments carry the words around the mask so `...args` or `***bold***` stay writable. `raise_if_integrity_rejection` raises the read, full-read and version rejections as ToolError for both write paths. | ✅ |
| file_activity_tracker.py | Core | File activity tracker. Line-level conflict detection for concurrent subagent file operations. | ✅ |
| file_edit_normalizer.py | Util | LLM input normalizer for file_edit_tool legacy flat fields（`normalize_edits_payload`、`merge_edits_for_diff`） | ✅ |
| file_read/ | Submodule | `file_read_tool` execution: multimodal blocks, text pages, truncation, outlines and read-scope guards (`multimodal.py`, `text_paths.py`, `truncation.py`, `outline.py`, `scope.py`). | ✅ |
| parked_file_view.py | Internal | View rules for a long text the context guard parked in `.myrm/pastes` or `.myrm/spillover`: `is_parked_path` (normalised-path test), `wrap_long_lines` (split a long line into rows after redacting it, so a secret cannot straddle a row boundary and escape the tool-output redaction), `wrapped_rows_notice`, `page_token_budget` (tokens in one page: 20,000, or a tenth of the model's window, at least 2,000, when the run reports a window of 65,536 or less), `parked_page_chars` (the characters of a page of that many tokens instead of the 10,000-character code-file page; only the window that becomes the page is measured). Every other file keeps the code-file read caps. | ✅ |
| mcp_read_next_step_hint.py | Util | One-shot MCP workflow reminder appended after batch-read of function docs | ✅ |

## Key Dependencies

- `backends`
- `toolkits`
- `utils`
