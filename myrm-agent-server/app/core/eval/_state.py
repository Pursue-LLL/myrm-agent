"""Shared eval state — matrix and layered evaluation coordination.

[INPUT]
- app.core.eval.reports::DEFAULT_REPORTS_DIR

[OUTPUT]
- matrix_state: shared progress dict mutated in place by both the matrix
  (app.core.eval.matrix) and layered (app.core.eval.layered) evaluation
  suites, so the Eval Lab matrix tab streams one unified progress.
- active_matrix_runner: shared binding for the runner currently being
  orchestrated. Modules must access it as ``eval_state.active_matrix_runner``
  (module attribute) — a plain ``from ... import name`` + ``global name =``
  would only rebind the importing module's local name and silently break
  cross-module abort.
- DEFAULT_MATRIX_REPORTS_DIR: shared report directory.

[POS]
Both eval variants reuse the same state machine and report directory on
purpose; this module is the single coordination point that avoids a circular
dependency between matrix and layered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.eval.reports import DEFAULT_REPORTS_DIR

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MatrixRunner

matrix_state: dict[str, object] = {
    "is_running": False,
    "current_profile": None,
    "profile_progress": 0,
    "profile_total": 0,
    "case_completed": 0,
    "case_total": 0,
    "error": None,
}

active_matrix_runner: "MatrixRunner | None" = None

DEFAULT_MATRIX_REPORTS_DIR = DEFAULT_REPORTS_DIR.parent / "matrix_reports"

__all__ = [
    "DEFAULT_MATRIX_REPORTS_DIR",
    "active_matrix_runner",
    "matrix_state",
]
