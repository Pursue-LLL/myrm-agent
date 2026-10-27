"""The checklist's frontend and browser verification warnings."""

from __future__ import annotations

from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import (
    build_checklist,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    VerificationCategory,
)


class TestFrontendBrowserVerificationWarning:
    """Test frontend rendering file detection triggers browser verification warning."""

    def test_frontend_tsx_without_browser_warns(self) -> None:
        """Modified .tsx file + no browser usage = WARNING in checklist."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/components/GoalCard.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "bun test"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "Frontend rendering files were modified" in checklist
        assert "browser" in checklist.lower()

    def test_frontend_css_without_browser_warns(self) -> None:
        """Modified .css file + no browser usage = WARNING."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/app/styles/globals.css"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" in checklist

    def test_frontend_with_browser_no_warning(self) -> None:
        """Modified .tsx + browser tools used = NO frontend warning."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/components/Header.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="browser_snapshot_tool",
                args_hash="snap1",
                args={},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist
        assert "Verify browser interactions" in checklist

    def test_test_tsx_no_warning(self) -> None:
        """Modified .test.tsx file should NOT trigger warning (non-render)."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/app/__tests__/GoalCard.test.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "vitest"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist

    def test_store_tsx_no_warning(self) -> None:
        """Modified store .ts file should NOT trigger warning."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/store/usePlanStore.ts"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "bun test"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist

    def test_config_file_no_warning(self) -> None:
        """Modified .config.ts should NOT trigger warning."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/tailwind.config.ts"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist

    def test_scss_without_browser_warns(self) -> None:
        """Modified .scss file + no browser usage = WARNING."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/app/styles/components/card.scss"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "npm run build"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.BUILD,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" in checklist

    def test_util_tsx_no_warning(self) -> None:
        """Modified util .tsx should NOT trigger warning."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/utils/formatDate.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "bun test"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist

    def test_type_selector_tsx_triggers_warning(self) -> None:
        """TypeSelector.tsx should trigger warning (path segment match, not substring)."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/components/TypeSelector.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "bun test"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" in checklist

    def test_types_folder_tsx_no_warning(self) -> None:
        """File in types/ folder should NOT trigger warning."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/types/Button.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "bun test"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist

    def test_astro_file_triggers_warning(self) -> None:
        """Modified .astro file should trigger warning."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="abc",
                args={"path": "/app/pages/index.astro"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" in checklist

    def test_stories_file_no_warning(self) -> None:
        """Storybook .stories.tsx should NOT trigger warning."""
        records = [
            CallRecord(
                tool_name="file_edit_tool",
                args_hash="abc",
                args={"path": "/app/components/Button.stories.tsx"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="def",
                args={"command": "bun test"},
                success_level=SuccessLevel.FULL_SUCCESS,
                verification_type=VerificationCategory.TEST,
            ),
        ]
        checklist, _ = build_checklist(records)
        assert "Frontend rendering files were modified" not in checklist

    def test_execute_failure_critical_when_writes_exist(self) -> None:
        """EXECUTE failures are CRITICAL when file writes exist."""
        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/src/main.py", "content": "x"},
                success_level=SuccessLevel.FULL_SUCCESS,
            ),
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="e1",
                args={"command": "pytest"},
                success_level=SuccessLevel.FAILURE,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert has_critical
        assert "CRITICAL" in checklist

    def test_execute_failure_warning_when_no_writes(self) -> None:
        """EXECUTE failures are only WARNING when no file writes (query task)."""
        records = [
            CallRecord(
                tool_name="bash_code_execute_tool",
                args_hash="e1",
                args={"command": "curl https://api.example.com"},
                success_level=SuccessLevel.FAILURE,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "WARNING" in checklist
        assert "CRITICAL" not in checklist

    def test_internal_tool_records_filtered(self) -> None:
        """CallRecords from internal tools (starting with _) are excluded."""
        records = [
            CallRecord(
                tool_name="_internal_probe",
                args_hash="ic1",
                args={"workspace_root": "/tmp"},
                success_level=SuccessLevel.FAILURE,
            ),
        ]
        checklist, has_critical = build_checklist(records)
        assert not has_critical
        assert "_internal_probe" not in checklist
        assert "Confirm the response fully addresses" in checklist
