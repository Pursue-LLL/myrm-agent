"""Memory Archive restore domain: journaled safe-merge recovery + rollback ledger.

[INPUT]
- Archive manifest payloads + partition data produced by ``archive.py``
  (POS: ``services.memory.archive.archive``).
- Read-only current memory DB state (planner) / restore ledger rows (executor,
  rollback) from the local SQLite.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``restore`` subpackage:
  - archive_restore: MemoryArchiveRestoreService / ArchiveRestoreHealth (dry-run,
    hash-verified, safe-merge restore; replay partition is `section_not_supported`)
  - archive_restore_common: shared restore constants, validation helpers,
    mutation-ref building, JSON coercion primitives
  - archive_restore_executor: MemoryArchiveRestoreExecutor (writes + ledger)
  - archive_restore_planner: MemoryArchiveRestorePlanner (section-level dry-run)
  - archive_restore_rollback: MemoryArchiveRestoreRollbacker (precise undo)

[POS]
Server business layer. Single restore domain inside the memory archive package:
planner/executor/rollbacker share the common primitives and are always used
together, so they stay co-located under one facade.
"""

from app.services.memory.archive.restore.archive_restore import (
    ArchiveRestoreHealth,
    MemoryArchiveRestoreService,
)
from app.services.memory.archive.restore.archive_restore_common import (
    MemoryArchiveRestoreError,
    add_restore_item,
    count_items,
    int_value,
    item_to_ref,
    make_ref,
    mark_restore_item,
    object_dict,
    object_rows,
    operation_status,
    optional_int,
    optional_str,
    parse_datetime,
    parse_datetime_or_none,
    refs_by_import_item,
    selected_sections,
)
from app.services.memory.archive.restore.archive_restore_executor import (
    MemoryArchiveRestoreExecutor,
)
from app.services.memory.archive.restore.archive_restore_planner import (
    MemoryArchiveRestorePlanner,
)
from app.services.memory.archive.restore.archive_restore_rollback import (
    MemoryArchiveRestoreRollbacker,
)

__all__ = [
    "ArchiveRestoreHealth",
    "MemoryArchiveRestoreError",
    "MemoryArchiveRestoreExecutor",
    "MemoryArchiveRestorePlanner",
    "MemoryArchiveRestoreRollbacker",
    "MemoryArchiveRestoreService",
    "add_restore_item",
    "count_items",
    "int_value",
    "item_to_ref",
    "make_ref",
    "mark_restore_item",
    "object_dict",
    "object_rows",
    "operation_status",
    "optional_int",
    "optional_str",
    "parse_datetime",
    "parse_datetime_or_none",
    "refs_by_import_item",
    "selected_sections",
]
