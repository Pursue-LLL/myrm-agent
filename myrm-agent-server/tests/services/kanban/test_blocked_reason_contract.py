"""Contract: shared/config/kanban_blocked_reasons.json holds exactly the blocked reasons the server translates for users.

[INPUT]
- shared/config/kanban_blocked_reasons.json (POS: the sentences the frontend matches against, read here only)
- app.services.kanban.task_runner.worktree.landing_gate::PARENT_MERGE_FAILED_REASON (POS: the sentence written to a held dependent)

[OUTPUT]
Fails when the server's sentence and the shared file differ, which would silently show the English sentence to users.

[POS]
tests/services/kanban/test_blocked_reason_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.kanban.task_runner.worktree.landing_gate import PARENT_MERGE_FAILED_REASON

_REASONS_PATH = Path(__file__).resolve().parents[4] / "shared" / "config" / "kanban_blocked_reasons.json"


def test_the_shared_file_lists_exactly_the_sentences_the_server_writes() -> None:
    assert json.loads(_REASONS_PATH.read_text(encoding="utf-8")) == {"parentMergeFailed": PARENT_MERGE_FAILED_REASON}
