"""Contract: shared/config/kanban_blocked_reasons.json holds exactly the blocked reasons the server owns and translates for users.

[INPUT]
- shared/config/kanban_blocked_reasons.json (POS: the sentences the frontend matches against, read here only)
- app.services.kanban.task_runner.worktree.landing_gate::PARENT_MERGE_FAILED_REASON (POS: written to a dependent held by a failed parent merge)
- app.services.kanban.task_runner.runner::_USAGE_LIMIT_BLOCK_REASON (POS: written to a task waiting for the provider's usage limit to reset)
- app.services.batch_directory._helpers::_BATCH_PAUSE_BLOCK_REASON (POS: written to a task frozen with its batch; also the marker the batch resume filters on)

[OUTPUT]
Fails when a server constant and the shared file differ, which would silently show the raw text to users.

[POS]
tests/services/kanban/test_blocked_reason_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.batch_directory._helpers import _BATCH_PAUSE_BLOCK_REASON
from app.services.kanban.task_runner.runner import _USAGE_LIMIT_BLOCK_REASON
from app.services.kanban.task_runner.worktree.landing_gate import PARENT_MERGE_FAILED_REASON

_REASONS_PATH = Path(__file__).resolve().parents[4] / "shared" / "config" / "kanban_blocked_reasons.json"


def test_the_shared_file_lists_exactly_the_reasons_the_server_owns() -> None:
    assert json.loads(_REASONS_PATH.read_text(encoding="utf-8")) == {
        "parentMergeFailed": PARENT_MERGE_FAILED_REASON,
        "usageLimit": _USAGE_LIMIT_BLOCK_REASON,
        "batchPause": _BATCH_PAUSE_BLOCK_REASON,
    }
