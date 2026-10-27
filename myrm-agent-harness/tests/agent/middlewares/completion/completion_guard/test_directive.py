"""What the model reads when the guard holds an answer back."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares.completion.completion_guard.directive import (
    BlockReasons,
    render_completion_directive,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
)


class TestCompletionDirective:
    """What the model reads for a held-back answer."""

    def test_directive_returns_checklist(self) -> None:
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/tmp/out.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]

        result = render_completion_directive(BlockReasons(), records=records, workspace_root=None)

        assert "file_write_tool" in result

    def test_forced_finish_directive(self) -> None:
        result = render_completion_directive(BlockReasons(forced_finish=True), records=[], workspace_root=None)
        assert "CRITICAL SYSTEM DIRECTIVE" in result

    def test_forced_finish_includes_staged_deliverable_notice(self) -> None:
        result = render_completion_directive(
            BlockReasons(
                forced_finish=True,
                staged_artifacts=({"filename": "draft_worker.py"},),
                execution_claim="unbacked claim",
            ),
            records=[],
            workspace_root=None,
        )
        assert "draft_worker.py" in result
        assert "claimed work" in result

    @pytest.mark.parametrize(
        "reason",
        ["evidence", "deliverable_write", "query_grounding", "ppt_outline"],
    )
    def test_forced_finish_states_what_is_still_unresolved(self, reason: str) -> None:
        result = render_completion_directive(
            BlockReasons(forced_finish=True, **{reason: "the unresolved point"}), records=[], workspace_root=None
        )
        assert "Still unresolved (the unresolved point)" in result

    @pytest.mark.parametrize(
        ("reasons", "marker"),
        [
            (
                BlockReasons(deliverable_write="claim without write"),
                "Deliverable write claim without tool evidence",
            ),
            (
                BlockReasons(execution_claim="claim without execution"),
                "Completion claim without executed evidence",
            ),
            (
                BlockReasons(query_grounding="ungrounded entity query"),
                "Entity query observation ungrounded",
            ),
            (
                BlockReasons(ppt_outline="weak outline"),
                "PPT Reporting Plan Outline Quality Gate Failed",
            ),
        ],
    )
    def test_directive_reports_each_block_reason(self, reasons: BlockReasons, marker: str) -> None:
        result = render_completion_directive(reasons, records=[], workspace_root=None)
        assert marker in result

    def test_a_directive_is_not_padded_with_a_leading_space(self) -> None:
        result = render_completion_directive(BlockReasons(evidence="x"), records=[], workspace_root=None)
        assert result.startswith("CRITICAL COMPLETION CHECK")
