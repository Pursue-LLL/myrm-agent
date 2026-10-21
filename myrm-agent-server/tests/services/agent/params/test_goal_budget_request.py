"""GoalBudgetRequest model unit tests.

Validates that all GoalBudget dimensions (max_tokens, max_usd, max_time_seconds,
max_turns) plus protected_paths, constraints, and control fields are properly
accepted, defaulted, and serialized by the Pydantic model.
"""

import pytest
from pydantic import ValidationError

from app.services.agent.params.models import GoalBudgetRequest


class TestGoalBudgetRequestFields:
    def test_all_fields_present(self):
        req = GoalBudgetRequest(
            max_tokens=50000,
            max_usd=5.0,
            max_time_seconds=3600,
            max_turns=30,
            convergence_window=3,
            loop_on_pause=True,
            max_loop_restarts=5,
            acceptance_criteria=[{"type": "shell", "command": "pytest"}],
            constraints=["Do not delete files"],
            protected_paths=["*.env", "config/**"],
            ui_summary="Test goal",
        )
        assert req.max_tokens == 50000
        assert req.max_usd == 5.0
        assert req.max_time_seconds == 3600
        assert req.max_turns == 30
        assert req.convergence_window == 3
        assert req.loop_on_pause is True
        assert req.max_loop_restarts == 5
        assert req.acceptance_criteria == [{"type": "shell", "command": "pytest"}]
        assert req.constraints == ["Do not delete files"]
        assert req.protected_paths == ["*.env", "config/**"]
        assert req.ui_summary == "Test goal"

    def test_defaults_all_none(self):
        req = GoalBudgetRequest()
        assert req.max_tokens is None
        assert req.max_usd is None
        assert req.max_time_seconds is None
        assert req.max_turns is None
        assert req.convergence_window is None
        assert req.loop_on_pause is False
        assert req.max_loop_restarts == 10
        assert req.acceptance_criteria is None
        assert req.constraints is None
        assert req.protected_paths is None
        assert req.ui_summary == ""

    def test_max_turns_only(self):
        req = GoalBudgetRequest(max_turns=25)
        assert req.max_turns == 25
        assert req.max_tokens is None

    def test_protected_paths_only(self):
        req = GoalBudgetRequest(protected_paths=["secrets.yaml", "*.pem"])
        assert req.protected_paths == ["secrets.yaml", "*.pem"]
        assert req.max_turns is None

    def test_ui_summary_max_length(self):
        short = GoalBudgetRequest(ui_summary="a" * 120)
        assert len(short.ui_summary) == 120

        with pytest.raises(ValidationError):
            GoalBudgetRequest(ui_summary="a" * 121)


class TestGoalBudgetRequestCamelAlias:
    def test_camel_case_alias_parsing(self):
        req = GoalBudgetRequest.model_validate(
            {
                "maxTokens": 10000,
                "maxUsd": 2.5,
                "maxTimeSeconds": 1800,
                "maxTurns": 15,
                "convergenceWindow": 3,
                "loopOnPause": True,
                "maxLoopRestarts": 8,
                "protectedPaths": ["*.key"],
                "uiSummary": "Camel test",
            }
        )
        assert req.max_tokens == 10000
        assert req.max_usd == 2.5
        assert req.max_time_seconds == 1800
        assert req.max_turns == 15
        assert req.convergence_window == 3
        assert req.loop_on_pause is True
        assert req.max_loop_restarts == 8
        assert req.protected_paths == ["*.key"]
        assert req.ui_summary == "Camel test"

    def test_snake_case_also_works(self):
        req = GoalBudgetRequest.model_validate(
            {
                "max_tokens": 5000,
                "max_turns": 10,
                "protected_paths": ["Dockerfile"],
            }
        )
        assert req.max_tokens == 5000
        assert req.max_turns == 10
        assert req.protected_paths == ["Dockerfile"]


class TestGoalBudgetRequestEdgeCases:
    def test_empty_protected_paths_list(self):
        req = GoalBudgetRequest(protected_paths=[])
        assert req.protected_paths == []

    def test_empty_constraints_list(self):
        req = GoalBudgetRequest(constraints=[])
        assert req.constraints == []

    def test_zero_budget_values(self):
        req = GoalBudgetRequest(max_tokens=0, max_usd=0.0, max_time_seconds=0, max_turns=0)
        assert req.max_tokens == 0
        assert req.max_usd == 0.0
        assert req.max_time_seconds == 0
        assert req.max_turns == 0

    def test_negative_values_accepted_by_model(self):
        req = GoalBudgetRequest(max_tokens=-1, max_usd=-0.5)
        assert req.max_tokens == -1
        assert req.max_usd == -0.5

    def test_acceptance_criteria_complex(self):
        criteria = [
            {"type": "shell", "command": "pytest tests/", "timeout_seconds": 120},
            {"type": "semantic", "criteria": "All tests pass", "target_file": "report.md"},
        ]
        req = GoalBudgetRequest(acceptance_criteria=criteria)
        assert len(req.acceptance_criteria) == 2
        assert req.acceptance_criteria[0]["type"] == "shell"
        assert req.acceptance_criteria[1]["type"] == "semantic"
