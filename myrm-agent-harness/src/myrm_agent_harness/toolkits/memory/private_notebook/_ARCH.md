# private_notebook/

## 1. Purpose

A long-running agent that only compacts its history into summaries loses detail: rejected hypotheses, error signatures and negative results disappear and get tried again later. The private notebook keeps that material outside the context window in two inspectable stores:
- **Notes**: Markdown files the model appends to or rewrites, one per title, under `<workspace>/.myrm/agent_notes/`. They are plain files, so a person can read, review and correct them.
- **History**: an in-memory catalog of the turns recorded per context window, searchable across the archived windows.

A context rotation switches to a fresh window id and writes a handover note into the notes, so the notes and the workspace carry over while the window starts clean. A bounded fallback summary of the last turns is available for hosts that need one.

## 2. Component Design

- `models.py`: immutable data contracts (`NoteEntry`, `NoteMetadata`, `NoteSearchResult`, `HistoryContextItem`, `HistoryEntryItem`, `NewContextResult`).
- `storage.py`: `LocalInspectableNoteStorage` — thread-safe disk I/O, keyword token matching, safe file-name sanitization and atomic overwrite.
- `history_manager.py`: `HistoryContextManager` — thread-safe per-window turn catalog with listing, reading and case-insensitive keyword search.
- `tools.py`: `PrivateNotebookToolKit` — the 10 model-facing tools (History 4 + Notes 5 + NewContext 1) as methods bound to a manager.
- `manager.py`: `ModelPrivateNotebookManager` — owns the storage, the history, the active context id and the rotation handover.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Package facade: the single import point for the manager, storage, history manager, toolkit, filename helper and data models. | ✅ |
| `history_manager.py` | Core | Thread-safe catalog of the turns recorded per context window, with listing, reading and keyword search across archived contexts. | ✅ |
| `manager.py` | Core | Orchestrator that owns the notes storage, the history index and the active context id, rotates to a fresh context with a handover note, and offers a bounded fallback summary. | ✅ |
| `models.py` | Types | Immutable note, search-hit, history-context and context-switch models. | ✅ |
| `storage.py` | Core | Thread-safe, human-inspectable Markdown note files with sanitized file names, atomic rewrites and keyword search. | ✅ |
| `tools.py` | Core | The 10 model-facing tools for notes, history recall and context handover, bound to a manager. | ✅ |
