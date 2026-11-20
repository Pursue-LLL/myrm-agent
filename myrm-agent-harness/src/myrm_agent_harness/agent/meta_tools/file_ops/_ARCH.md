# file_ops/

## Overview
File operations tool module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | File operations tool module. | — |
| constants.py | Core | Constants, including the read size limits: `MAX_FILE_READ_SIZE_BYTES` for a whole-file read, the higher `MAX_RANGED_READ_SIZE_BYTES` for a read with a line range (the way into a big file), and `REASON_FIELD_DESCRIPTION`, the `reason` parameter text the three file tools share. | ✅ |
| executor_storage_adapter.py | Core | CodeExecutor to StorageProvider adapter. | ✅ |
| file_edit_tool.py | Core | Batch atomic file edit via edits[]; LLM payload normalizer; whitespace-tolerant matching (a block whose lines differ is refused). A failed match carries the hint for its kind (`EditMatchError.kind`: not found, matches more than once, overlaps another edit), not one picked from the wording of the message. The parameter schema is one English text for every locale; only the description head is localized, and it states the read-before-edit rule with its exceptions | ✅ |
| file_read_tool.py | Core | File read tool factory: local/MCP/**vault://** paths, Pydantic alias mapping, pre-IO device and network-share protection (decided on the path text, before any filesystem call), Unicode auto-healing of a path that names nothing (`core.security.path.find_existing_unicode_path`; the permission engine judges the typed and the healed spelling alike, and the healer never lands on a device or on a credential file the typed text does not name), batch reads, line ranges, multimodal; the Fast-track scope allows UECD spill, uploads and the spilled long-paste directories (`context_guard` constants) and rejects `..` escapes (guards in `core/file_read/scope.py`). The parameter schema is one English text for every locale; only the description head is localized | ✅ |
| file_write_tool.py | Core | File write tool. Creates new files (missing parent directories included); rejects empty/whitespace-only content and paths that already exist. Same one-English-schema rule as the other two tools | ✅ |
| revert_service.py | Core | File revert service — undo AI file changes of a message or of a whole session; surfaces revertible/skip_reason; skips non-revertible snapshots and non-UTF-8 files on revert; records each restored file as modified and each created file it removed as deleted in the artifact trail of the session it is for (a revert runs outside any agent turn, so the session comes from the call, not from a bound chat). | ✅ |
| validators/ | Submodule | Pre/post write validators including vault markdown FM guard and Office text-write warnings. | ✅ |
| streaming.py | Core | File streaming reader. Two readers behind `stream` / `preview` mode: `read_file_chunked(max_chars=)` reads in chunks and stops exactly one character past the cap so a caller can tell the file goes on; `read_file_preview` returns the first lines plus a hint to read on. | ✅ |

| Submodule | Description |
|-----------|-------------|
| core/ | Text Editor core business logic module. |
| observers/ | Observers module. |
| strategies/ | File system strategy module. |
| utils/ | Utility functions module. |
| validators/ | Validators module. |

## Key Dependencies

- `backends`
- `toolkits`
- `utils`
