"""Transparent, inspectable model private notebook package.

[INPUT]
- toolkits.memory.private_notebook.history_manager::HistoryContextManager (POS: History layer of the private notebook: a thread-safe catalog of the turns recorded per context window, with listing, reading and case-insensitive keyword search across archived contexts.)
- toolkits.memory.private_notebook.manager::ModelPrivateNotebookManager (POS: Orchestrator of the private notebook: owns the notes storage under `<workspace>/.myrm/agent_notes`, the history index and the active context id, rotates to a fresh context while writing a handover note, and offers a bounded fallback summary of recent turns.)
- toolkits.memory.private_notebook.models::HistoryContextItem, HistoryEntryItem, NewContextResult, NoteEntry, NoteMetadata, NoteSearchResult (POS: Contract layer of the private notebook: the immutable note, search-hit, history-context and context-switch models shared by the storage, the history manager and the manager.)
- toolkits.memory.private_notebook.storage::LocalInspectableNoteStorage, sanitize_filename (POS: Notes layer of the private notebook: thread-safe, human-inspectable Markdown note files with sanitized file names, atomic rewrites and keyword search.)
- toolkits.memory.private_notebook.tools::PrivateNotebookToolKit (POS: Tool surface of the private notebook: packages the 10 model-facing tools (4 history, 5 notes, 1 context rotation) as methods of one toolkit bound to a manager.)

[OUTPUT]
- the manager, storage, history manager, toolkit, filename helper and data models listed in `__all__`

[POS]
Package facade of the private notebook: the single import point for the manager, storage, history manager, toolkit and the
data models.
"""

from .history_manager import HistoryContextManager
from .manager import ModelPrivateNotebookManager
from .models import (
    HistoryContextItem,
    HistoryEntryItem,
    NewContextResult,
    NoteEntry,
    NoteMetadata,
    NoteSearchResult,
)
from .storage import LocalInspectableNoteStorage, sanitize_filename
from .tools import PrivateNotebookToolKit

__all__ = [
    "HistoryContextItem",
    "HistoryContextManager",
    "HistoryEntryItem",
    "LocalInspectableNoteStorage",
    "ModelPrivateNotebookManager",
    "NewContextResult",
    "NoteEntry",
    "NoteMetadata",
    "NoteSearchResult",
    "PrivateNotebookToolKit",
    "sanitize_filename",
]
