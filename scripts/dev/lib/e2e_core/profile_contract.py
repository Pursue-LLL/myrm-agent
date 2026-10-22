"""Shared Chrome E2E profile reason contract.

The launcher and pytest plugin validate the same private-mode reason set. Keeping
the enum in the dev library prevents the two entry points from silently drifting.
"""

from __future__ import annotations

from typing import Final

PRIVATE_REASONS: Final[frozenset[str]] = frozenset(
    {
        "live_shpoib",
        "fault_injection",
        "exclusive_backend",
        "global_write_non_namespace",
    }
)

UNSUPPORTED_PRIVATE_REASONS: Final[frozenset[str]] = frozenset(
    {"process_isolation"}
)

EXCLUSIVE_BACKEND_CEILING: Final[int] = 7

EXCLUSIVE_BACKEND_EVIDENCE_MANIFEST: Final[dict[tuple[str, str], str]] = {
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_memory_pending_batch_chrome_e2e.py",
        "test_memory_pending_batch_accept_reports_stale_and_reject_all_chrome_e2e",
    ): "configured_retrieval_embedding mutates global /api/v1/config/retrieval and batch-accepts/rejects instance-wide /api/v1/memory/pending queue",
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_memory_pending_dialog_chrome_e2e.py",
        "test_memory_pending_dialog_edit_then_accept_chrome_e2e",
    ): "configured_retrieval_embedding mutates global /api/v1/config/retrieval and mutates instance-wide /api/v1/memory/pending + semantic memory store",
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_memory_pending_dialog_chrome_e2e.py",
        "test_memory_pending_dialog_reject_keeps_target_chrome_e2e",
    ): "configured_retrieval_embedding mutates global /api/v1/config/retrieval and mutates instance-wide /api/v1/memory/pending + semantic memory store",
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_memory_pending_proposal_review_chrome_e2e.py",
        "test_memory_pending_proposal_review_chrome_e2e",
    ): "configured_retrieval_embedding mutates global /api/v1/config/retrieval and mutates instance-wide /api/v1/memory/pending + /api/v1/memory/trash",
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_memory_pending_proposal_review_chrome_e2e.py",
        "test_memory_pending_stale_target_refused_chrome_e2e",
    ): "configured_retrieval_embedding mutates global /api/v1/config/retrieval and exercises 409 conflict on instance-wide /api/v1/memory/pending",
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_pending_approvals_chrome_e2e.py",
        "test_fleet_pending_approvals_kpi_tracks_kanban_in_review",
    ): "asserts exact global /api/v1/statistics/overview pending_approvals delta (kpi_review == kpi_before + 1)",
    (
        "myrm-agent/myrm-agent-server/tests/e2e/test_skill_manage_undo_hint_chrome_e2e.py",
        "test_skill_manage_undo_hint_expands_task_steps",
    ): "seeds and rolls back global skill directory state via /api/v1/test/seed-skill-rollback-turn",
}

_EXCLUSIVE_BACKEND_BY_FILENAME: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        *(
            (rel_path.rsplit("/", 1)[-1], func_name)
            for rel_path, func_name in EXCLUSIVE_BACKEND_EVIDENCE_MANIFEST
        ),
        # Mechanical SSOT spread via e2e_core.guardrail_ssot.CHROME_E2E_MARKER_KWARGS
        (
            "test_guardrail_bash_chrome_e2e.py",
            "test_guardrail_bash_progress_step_and_safety_badge_render",
        ),
    }
)

CHROME_E2E_MAX_TIMEOUT_SEC: Final[int] = 600
CHROME_E2E_TIMEOUT_EXCEED_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "test_smart_routing_tier_chrome_e2e.py",
    }
)


def is_allowed_exclusive_backend_test(file_name: str, test_name: str) -> bool:
    """Return True only when ``(file_name, test_name)`` is in the M3 ratchet manifest."""
    clean_file = file_name.rsplit("/", 1)[-1].strip()
    clean_test = test_name.split("[", 1)[0].strip()
    return (clean_file, clean_test) in _EXCLUSIVE_BACKEND_BY_FILENAME

