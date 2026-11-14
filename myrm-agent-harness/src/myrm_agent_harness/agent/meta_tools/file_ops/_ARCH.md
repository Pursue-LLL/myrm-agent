# file_ops/

## Overview
File operations tool module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | File operations tool module. | — |
| constants.py | Core | Constants, including the read size limits: `MAX_FILE_READ_SIZE_BYTES` for a whole-file read, the higher `MAX_RANGED_READ_SIZE_BYTES` for a read with a line range (the way into a big file), and `REASON_FIELD_DESCRIPTION`, the `reason` parameter text the three file tools share. | ✅ |
| executor_storage_adapter.py | Core | CodeExecutor to StorageProvider adapter. | ✅ |
| file_edit_tool.py | Core | Batch atomic file edit via edits[]; LLM payload normalizer; whitespace-tolerant matching (a block whose lines differ is refused). The parameter schema is one English text for every locale; only the description head is localized, and it states the read-before-edit rule with its exceptions | ✅ |
| file_read_tool.py | Core | File read tool factory: local/MCP/File ID/**vault://** paths, Pydantic alias mapping, pre-IO device protection, Unicode auto-healing, batch reads, line ranges, multimodal; the Fast-track scope allows UECD spill, uploads and the spilled long-paste directories (`context_guard` constants) and rejects `..` escapes (guards in `core/file_read/scope.py`). The parameter schema is one English text for every locale; only the description head is localized | ✅ |
| file_write_tool.py | Core | File write tool. Creates new files (missing parent directories included); rejects empty/whitespace-only content and paths that already exist. Same one-English-schema rule as the other two tools | ✅ |
| revert_service.py | Core | File revert service — undo AI file changes; surfaces revertible/skip_reason; skips non-revertible snapshots and non-UTF-8 files on revert. | ✅ |
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
