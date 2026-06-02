"""Mascot state and emotional transition mapping service.

Translates low-level agent execution and sandbox events into intuitive,
highly-cohesive mascot animation and behavioral states.
"""

from enum import Enum


class MascotStatus(str, Enum):
    """Supported mascot animation and emotional states."""

    SLEEPING = "sleeping"  # Agent is idle
    THINKING = "thinking"  # Agent is running normal thoughts
    DIZZY = "dizzy"  # Compiler/Lint/Validation error detected
    CELEBRATING = "celebrating"  # Successful test run or Goal accomplished
    PANTING = "panting"  # High resource/Token budget warning


class MascotStateMapper:
    """Service to map low-level harness events to user-friendly Mascot states."""

    @staticmethod
    def map_event_to_mascot_state(
        event_type: str,
        payload: dict[str, object] | None = None,
    ) -> MascotStatus:
        """Map raw framework events into unified Mascot states.

        Args:
            event_type: The raw framework event name.
            payload: Optional payload dictionary containing metrics/metadata.

        Returns:
            The mapped MascotStatus.
        """
        payload = payload or {}

        # 1. Budget Enforcer Warnings
        if event_type in {"budget_warning", "token_limit_exceeded", "quota_warning"}:
            return MascotStatus.PANTING

        # 2. Compilation and Code Execution Failures
        if event_type in {"tool_error", "compile_error", "lint_warning"}:
            # We look closely if it is a validation failure
            error_cat = payload.get("error_category", "")
            if error_cat in {"compile", "lint", "runtime_error"}:
                return MascotStatus.DIZZY
            return MascotStatus.DIZZY

        # 3. Successful test runs or Goal state completions
        if event_type in {"goal_completed", "tests_passed", "verification_success"}:
            return MascotStatus.CELEBRATING

        # 4. Standard Agent Execution Lifecycle
        if event_type in {"agent_start", "agent_step", "tool_call_start"}:
            return MascotStatus.THINKING

        if event_type in {"agent_idle", "session_sleep"}:
            return MascotStatus.SLEEPING

        # Default fallbacks
        return MascotStatus.THINKING
